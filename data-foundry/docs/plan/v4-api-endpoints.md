API Endpoints Plan for v4-df-migration Features

     Question: Do v4-df-migration features require new API endpoints?

     Answer: YES - Verified by external partner review. The Week 1-3 migration features are production-ready internal libraries that need API
     endpoints for full operational use.

     ---
     External Review Verification

     Assessment: ACCURATE with one priority correction.

     Verified Current State

     | Component                    | Status         | Details                             |
     |------------------------------|----------------|-------------------------------------|
     | Registered Endpoints         | 7 total        | All in src/main.py                  |
     | Consent Router               | NOT REGISTERED | 8 GDPR endpoints ready but excluded |
     | Week 1 Quality Validator     | Internal only  | 32+ tests passing                   |
     | Week 2 A/B Testing           | Internal only  | 32+ tests passing                   |
     | Week 3 Signal Detection + ML | Internal only  | 90 tests passing                    |

     Priority Correction from External Review

     PHASE 1 MUST BE: Register consent router FIRST

     Why first?
     - 8 GDPR-compliant endpoints already fully implemented and tested
     - Zero new code needed - just 2-3 lines in main.py
     - Immediate business value (GDPR Article 7, 17, 20, 21 compliance)
     - Quick win before building new functionality

     ---
     Branch Strategy Recommendation

     Current Branch Status

     Branch: feature/v4-df-migration
     Status: Week 1-3 COMPLETE (production-ready)
     - Week 1: Data Quality Validator ✅
     - Week 2: A/B Testing Framework ✅
     - Week 3: Signal Detection + ML ✅
     Latest: 95d8e78

     Recommended Actions

     1. Merge feature/v4-df-migration to develop
     git checkout develop
     git merge feature/v4-df-migration
     git push origin develop

     2. Create new branch for API work
     git checkout -b feature/week-4-api-endpoints

     Why Separate Branches?

     - Clean git history (internal libs vs API layer)
     - Independent deployment capability
     - Easier rollback if API issues occur
     - Clear milestone tracking

     ---
     Implementation Plan (Week 4)

     Phase 1: Fix Consent Router (1-2 hours) - HIGHEST PRIORITY

     File: src/main.py

     Changes:
     # Add import
     from src.api.v1.consent.router import router as consent_router

     # Add registration (before app definition ends)
     app.include_router(consent_router, prefix="/api/v1")

     Immediate Value - 8 GDPR Endpoints:
     - POST /api/v1/consent/grant
     - POST /api/v1/consent/withdraw
     - GET /api/v1/consent/verify/{user_id}/{consent_type}
     - POST /api/v1/consent/object
     - GET /api/v1/consent/user/{user_id}
     - DELETE /api/v1/consent/user/{user_id}
     - GET /api/v1/consent/user/{user_id}/export
     - GET /api/v1/consent/user/{user_id}/history

     Phase 2: Create New API Routers (5 routers, ~26-30 endpoints)

     2.1 Data Quality API

     Files to create:
     - src/api/v1/quality/router.py (~200 lines)
     - src/api/v1/quality/contracts.py (~100 lines) - Pydantic models

     Endpoints:
     POST   /api/v1/quality/validate          # Validate single record
     POST   /api/v1/quality/validate-batch   # Validate batch
     GET    /api/v1/quality/metrics          # Quality metrics
     GET    /api/v1/quality/config           # Get config
     PUT    /api/v1/quality/config           # Update weights (admin)

     2.2 A/B Testing API

     Files to create:
     - src/api/v1/abtest/router.py (~250 lines)
     - src/api/v1/abtest/contracts.py (~150 lines)

     Endpoints:
     POST   /api/v1/abtest/create            # Create A/B test
     GET    /api/v1/abtest/list              # List tests
     GET    /api/v1/abtest/{test_id}/stats   # Test statistics
     POST   /api/v1/abtest/{test_id}/record  # Record prediction
     GET    /api/v1/abtest/{test_id}/metrics # Full metrics
     GET    /api/v1/abtest/{test_id}/export  # Export JSON
     PUT    /api/v1/abtest/{test_id}/ratio   # Adjust ratio (admin)

     2.3 Signal Detection API

     Files to create:
     - src/api/v1/signals/router.py (~200 lines)
     - src/api/v1/signals/contracts.py (~100 lines)

     Endpoints:
     POST   /api/v1/signals/detect           # Detect signals
     POST   /api/v1/signals/detect-batch    # Batch detect
     GET    /api/v1/signals/config           # Get config
     PUT    /api/v1/signals/config           # Update config (admin)
     GET    /api/v1/signals/types            # List signal types

     2.4 ML Predictor API

     Files to create:
     - src/api/v1/ml/router.py (~200 lines)
     - src/api/v1/ml/contracts.py (~100 lines)

     Endpoints:
     POST   /api/v1/ml/predict               # Predict quality
     POST   /api/v1/ml/predict-batch        # Batch predict
     GET    /api/v1/ml/model/info            # Model metadata
     POST   /api/v1/ml/model/reload          # Reload model (admin)
     GET    /api/v1/ml/features/extract      # Extract features

     2.5 Admin/Monitoring API

     Files to create:
     - src/api/v1/admin/router.py (~200 lines)
     - src/api/v1/admin/contracts.py (~100 lines)

     Endpoints:
     GET    /api/v1/admin/health/detailed    # Component health
     GET    /api/v1/admin/metrics/aggregated # Aggregated metrics
     GET    /api/v1/admin/pipeline/status    # Pipeline status
     POST   /api/v1/admin/pipeline/trigger   # Trigger pipeline

     ---
     Files Summary

     Create (10 new files)

     | File                            | Lines | Purpose                        |
     |---------------------------------|-------|--------------------------------|
     | src/api/v1/quality/router.py    | ~200  | Data Quality API endpoints     |
     | src/api/v1/quality/contracts.py | ~100  | Pydantic models                |
     | src/api/v1/abtest/router.py     | ~250  | A/B Testing API endpoints      |
     | src/api/v1/abtest/contracts.py  | ~150  | Pydantic models                |
     | src/api/v1/signals/router.py    | ~200  | Signal Detection API endpoints |
     | src/api/v1/signals/contracts.py | ~100  | Pydantic models                |
     | src/api/v1/ml/router.py         | ~200  | ML Predictor API endpoints     |
     | src/api/v1/ml/contracts.py      | ~100  | Pydantic models                |
     | src/api/v1/admin/router.py      | ~200  | Admin/Monitoring API endpoints |
     | src/api/v1/admin/contracts.py   | ~100  | Pydantic models                |

     Modify (1 file)

     | File        | Changes                                           |
     |-------------|---------------------------------------------------|
     | src/main.py | Add consent router import + include 5 new routers |

     ---
     Implementation Considerations

     Authentication & Authorization

     - Use get_current_user_token dependency for authentication
     - Implement role-based access for admin endpoints
     - Follow consent router's security patterns

     Request/Response Models

     - Pydantic models in contracts.py files
     - Input validation
     - OpenAPI/Swagger documentation
     - Type safety

     Error Handling

     - Follow consent router patterns
     - Standard HTTP status codes
     - Structured error responses
     - Rate limiting where appropriate

     Testing

     For each new router:
     - Unit tests for endpoints
     - Integration tests with core libraries
     - Authentication/authorization tests
     - Rate limiting tests (if applicable)

     ---
     Final Endpoint Count

     | Category                   | Count  |
     |----------------------------|--------|
     | Current registered         | 7      |
     | Consent (unregistered)     | 8      |
     | New routers                | ~26-30 |
     | Total after implementation | ~41-45 |

     ---
     Risk Assessment

     | Risk Level | Items                                                                                   |
     |------------|-----------------------------------------------------------------------------------------|
     | Low        | Core libraries tested (90+ tests), API is thin wrapper, consent router provides pattern |
     | Medium     | Consistent auth across endpoints, admin endpoint authorization, rate limiting config    |

     Mitigation: Follow consent router patterns exactly, comprehensive endpoint testing, security review for admin endpoints.

     ---
     Estimated Timeline

     | Phase                      | Duration   |
     |----------------------------|------------|
     | Phase 1: Consent router    | 1-2 hours  |
     | Phase 2: Quality API       | 2-3 days   |
     | Phase 3: Remaining routers | 5-7 days   |
     | Total                      | ~1-2 weeks |

     ---
     Implementation Order

     1. Fix consent router - Add include_router to main.py (1-2 hours)
     2. Create quality router - Data Quality Validator endpoints (2-3 days)
     3. Create abtest router - A/B Testing endpoints (1-2 days)
     4. Create signals router - Signal Detection endpoints (1-2 days)
     5. Create ml router - ML Predictor endpoints (1-2 days)
     6. Create admin router - Admin/Monitoring endpoints (1 day)
     7. Update main.py - Register all new routers
     8. Add tests - API integration tests for all endpoints

     ---
     Summary

     Answer: YES - New API endpoints are required for v4-df-migration features.

     - Current: 7 endpoints (plus 8 unregistered consent endpoints)
     - After implementation: ~41-45 endpoints
     - New routers: 5
     - New endpoints: ~26-30

     The v4-df-migration features (Week 1-3) are production-ready internal libraries but lack API exposure for operational use, monitoring, and
     administration