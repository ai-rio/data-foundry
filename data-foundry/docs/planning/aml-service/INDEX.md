# AML Service - Documentation Index

## Overview
Regulatory expertise service for fintech AML compliance. Focus on high-risk cross-border transfer labeling with perfect accuracy and audit-ready documentation.

---

## Documentation Structure

### 1. **MLP_SPECIFICATION.md** ✅
Minimum Lovable Product (MLP) specification for AML service
- Executive summary: Why MLP (not MVP) for AML
- Lovable core: Expertise-driven service, not feature platform
- Regulatory focus: High-risk cross-border transfers
- Target user: Fintech compliance officers
- Competitive differentiation: Trust over features
- Success metrics: 98%+ accuracy, customer advocacy

### 2. **IMPLEMENTATION_PLAN.md** ✅
Complete implementation roadmap for AML service
- Phase 1: Core labeling infrastructure (ORM, models, migrations)
- Phase 2: AI service integration (OpenAI, prompt engineering)
- Phase 3: Batch processing and orchestration
- Phase 4: API layer and endpoints
- Phase 5: Testing and validation
- Phase 6: Documentation and deployment

### 3. **REGULATORY_REFERENCE.md** ✅
Regulatory framework and compliance requirements
- FinCEN SAR requirements
- Cross-border transfer regulations
- AML typologies and red flags
- Label taxonomy and definitions
- Audit trail requirements

### 4. **CODEBASE_INVENTORY.md** ✅
Inventory of AML-related code components
- ORM models (AMLTransaction, AMLTransactionLabels)
- Database migrations (001-004)
- API endpoints and routes
- Task orchestration (Prefect flows)
- Test coverage summary

---

## Status

### Completed Components
- [x] MLP specification defined ✅
- [x] Regulatory framework researched ✅
- [x] Implementation plan completed ✅
- [x] ORM models created (AML_TRANSACTION_LABELS table) ✅
- [x] Database migrations (001-004) ✅
- [x] AI service integration (OpenAI) ✅
- [x] Batch processing (Prefect) ✅
- [x] API endpoints implemented ✅
- [x] End-to-end tests (P01-023) ✅

### Test Status
- **P01-023 Integration Tests**: 58% pass rate (11/19 tests passing)
- Fix migrations applied (migration 004: unique constraint)
- Mock patches corrected (src.services.ai_service.AIService)
- Test data isolation improved (unique timestamps)

---

## Service Architecture

### Core Components
1. **ORM Layer**: SQLAlchemy models for AML transactions and labels
2. **AI Integration**: OpenAI GPT-4 for labeling decisions
3. **Batch Processing**: Prefect workflows for async processing
4. **API Layer**: FastAPI endpoints for AML operations
5. **Database**: PostgreSQL with audit trails

### Data Flow
```
Transaction Data → Ingestion → AI Labeling → Quality Check → Storage → API Response
                   ↓              ↓               ↓            ↓
                 Prefect      OpenAI        Validation   PostgreSQL
                 Tasks       GPT-4          Logic      (Audit Trail)
```

---

## Key Features

### 1. Regulatory Expertise
- FinCEN SAR compliance
- Cross-border transfer specialization
- 8 regulatory flag types
- Audit-ready documentation

### 2. AI-Powered Labeling
- GPT-4 integration with expert prompts
- 98%+ accuracy target
- Explicit reasoning for each label
- Human-in-the-loop validation

### 3. Production-Ready Infrastructure
- Idempotent batch processing
- Unique constraint enforcement
- Comprehensive audit trails
- Error handling and rollback

---

## Next Steps

### Immediate (P0)
1. **Fix remaining test failures** - P01-023 (8/19 tests failing)
2. **Validate migration 004** - Ensure unique constraint working
3. **Complete API documentation** - OpenAPI spec

### Short-term (P1)
1. **Performance testing** - Load test batch processing
2. **Security audit** - Review API key handling
3. **User documentation** - Getting started guide

### Long-term (P2)
1. **Additional typologies** - Expand beyond cross-border
2. **Human review interface** - UI for validation
3. **Analytics dashboard** - Label quality metrics

---

## Related Documentation

- **Architecture**: See `architecture/` for system design
- **API**: See `api/` for endpoint specifications
- **Testing**: See `tests/tasks/test_aml_end_to_end.py`
- **Migrations**: See `src/database/migrations/003_*.py`, `004_*.py`

---

## Contact & Support

- **Project Lead**: Data Foundry Team
- **Documentation**: `/docs/planning/aml-service/`
- **Code**: `/src/tasks/ingestion.py`, `/src/models/aml/`
- **Tests**: `/tests/tasks/test_aml_end_to_end.py`
