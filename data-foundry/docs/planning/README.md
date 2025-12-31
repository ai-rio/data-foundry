# Planning Documentation

This directory contains planning documents and specifications for Data Foundry services and features.

---

## Active Services

### 1. [AML Service](./aml-service/)
**Regulatory expertise service for fintech AML compliance**

- **[INDEX.md](./aml-service/INDEX.md)** - Documentation index and overview
- **[MLP_SPECIFICATION.md](./aml-service/MLP_SPECIFICATION.md)** - Minimum Lovable Product specification
- **[IMPLEMENTATION_PLAN.md](./aml-service/IMPLEMENTATION_PLAN.md)** - Complete implementation roadmap
- **[REGULATORY_REFERENCE.md](./aml-service/REGULATORY_REFERENCE.md)** - FinCEN and compliance framework
- **[CODEBASE_INVENTORY.md](./aml-service/CODEBASE_INVENTORY.md)** - Code components inventory

**Status:** ✅ Implemented (P01-023)
**Test Coverage:** 58% (11/19 tests passing)
**Migration:** Migration 004 (unique constraint) applied

---

### 2. [Data Quality Service](./data-quality-service/)
**Self-contained data validation service for detecting bad data**

- **[INDEX.md](./data-quality-service/INDEX.md)** - Documentation index
- **[ARCHITECTURE.md](./data-quality-service/ARCHITECTURE.md)** - System architecture (8 components)
- **[API_SPECIFICATION.md](./data-quality-service/API_SPECIFICATION.md)** - Complete API contract
- **[E2E_FLOW.md](./data-quality-service/E2E_FLOW.md)** - End-to-end user flows
- **[INFRASTRUCTURE.md](./data-quality-service/INFRASTRUCTURE.md)** - Deployment requirements
- **[GO_TO_MARKET.md](./data-quality-service/GO_TO_MARKET.md)** - Launch strategy

**Status:** ✅ Documentation complete (106KB)
**Launch:** Production-ready

---

### 3. [Metering Service](./metering-service/)
**Stripe-based metered billing infrastructure**

- **[INDEX.md](./metering-service/INDEX.md)** - Documentation index
- **[ARCHITECTURE.md](./metering-service/ARCHITECTURE.md)** - System architecture
- **[API_SPECIFICATION.md](./metering-service/API_SPECIFICATION.md)** - API contract
- **[E2E_FLOW.md](./metering-service/E2E_FLOW.md)** - Billing flow documentation
- **[INFRASTRUCTURE.md](./metering-service/INFRASTRUCTURE.md)** - Infrastructure setup
- **[GO_TO_MARKET.md](./metering-service/GO_TO_MARKET.md)** - Go-to-market strategy

**Status:** ✅ Documentation complete
**Integration:** Stripe billing with usage-based pricing

---

## Archive

Historical planning documents organized by category:

### [Archive Structure](./archive/)

| Category | Files | Description |
|----------|-------|-------------|
| **architecture/** | 2 | Schema design, technology decisions |
| **backend/** | 1 | Backend validation prompts |
| **frontend/** | 2 | Frontend MDO strategy, analysis |
| **migration/** | 1 | P01-002 migration implementation |
| **misc/** | 1 | Documentation updates |
| **refactoring/** | 2 | Refactoring summaries, Stripe service |
| **stripe/** | 1 | Stripe metered billing requirements |
| **workflows/** | 1 | P01 execution workflow |

---

## Other Planning Documents

### Root-Level Planning
- **[STRIPE_SERVICE_REFACTORING_PLAN.md](./archive/refactoring/STRIPE_SERVICE_REFACTORING_PLAN.md)** - Stripe service refactoring (archived)
- **[REFACTORING_SUMMARY.md](./archive/refactoring/REFACTORING_SUMMARY.md)** - General refactoring summary (archived)

---

## Quick Links

- **Services:** [AML](./aml-service/) | [Data Quality](./data-quality-service/) | [Metering](./metering-service/)
- **Archive:** [Browse Archive](./archive/)
- **Main Docs:** [Return to Documentation Index](../)

---

## Documentation Standards

### Folder Structure
```
planning/
├── aml-service/           # Active service specifications
├── data-quality-service/  # Active service specifications
├── metering-service/      # Active service specifications
└── archive/               # Historical planning documents
    ├── architecture/
    ├── backend/
    ├── frontend/
    ├── migration/
    ├── misc/
    ├── refactoring/
    ├── stripe/
    └── workflows/
```

### File Naming Conventions
- Use **UPPERCASE_SNAKE_CASE** for planning documents (e.g., `IMPLEMENTATION_PLAN.md`)
- Use **lowercase** for service folders (e.g., `aml-service/`)
- Use **INDEX.md** for folder overview documents

### Document Template
When creating new planning documents, include:
1. **Document Status** (Draft, In Review, Approved, Archived)
2. **Date** (creation/last updated)
3. **Context** (why this document exists)
4. **Executive Summary** (brief overview)
5. **Detailed Content** (main body)
6. **Related Documents** (cross-references)

---

## Maintenance

### Adding New Service Planning
1. Create folder: `docs/planning/<service-name>/`
2. Add `INDEX.md` with overview
3. Add specification documents
4. Update this README with service details

### Archiving Documents
1. Move to `docs/planning/archive/<category>/`
2. Update archive index
3. Remove from active references

---

**Last Updated:** December 31, 2025
**Maintained By:** Data Foundry Team
