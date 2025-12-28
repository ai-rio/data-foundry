# Quick Reference: Gaps vs. Your Codebase

**One-page summary** of what's built, what's missing, and what to do next.

---

## Status Overview

```
████████████████████░  90% Complete (53k LOC)

✅ Backend:      95% (API, DB, Billing, Security, ML, Orchestration)
✅ Infrastructure: 100% (Docker, PostgreSQL, Redis, Prefect, Label Studio)
⚠️  Data Ingestion: 70% (Flow exists, needs abstraction layer)
⚠️  File Storage:   0% (No S3/R2 integration)
⚠️  Frontend:       5% (Repo exists, no components)
⚠️  Real-time:     0% (No WebSocket)
⚠️  Notifications: 0% (No SendGrid)
```

---

## Gap #1: Parser Abstraction Layer

| Aspect | Status | Issue | Solution |
|--------|--------|-------|----------|
| Lightweight parsers (CSV, JSON, PDF) | ✅ Deps exist | No abstraction | Create `src/services/parsers/` with factory |
| Heavyweight parser (Docling) | ⚠️ Planned | Not separated | Create stub, call microservice |
| File type detection | ❌ Missing | No tier checking | Add `src/core/file_detection.py` |
| Ingestion flow | ✅ Exists | Hardcoded logic | Refactor to use `ParserFactory` |

**Time:** 3-4 days | **Complexity:** Medium | **Priority:** 1️⃣ CRITICAL

---

## Gap #2: File Storage (S3/R2)

| Aspect | Status | Issue | Solution |
|--------|--------|-------|----------|
| S3/R2 client | ❌ Missing | Not in deps | Add boto3 + `StorageService` |
| Upload handler | ❌ Missing | No file upload | Create multipart upload handler |
| Download handler | ❌ Missing | No export | Create signed URL download |
| Retention policies | ❌ Missing | No cleanup | Add Prefect task for expiration |
| API endpoint | ❌ Missing | No routes | Create `src/api/v1/storage/` |

**Time:** 2-3 days | **Complexity:** Medium | **Priority:** 1️⃣ CRITICAL

---

## Gap #3: Frontend

| Page | Status | Components Needed | Time |
|------|--------|-------------------|------|
| **Upload** | ⚠️ 0% | FileUpload, TierDetection, CostEstimator | 2 days |
| **Monitor** | ⚠️ 0% | ProgressMonitor, StageTimeline, CostTracker | 2 days |
| **Results** | ⚠️ 0% | ResultsView, QualityReport, ExportOptions | 2 days |
| **Admin** | ⚠️ 0% | UserMgmt, DatasetMgmt, BillingHistory | 3 days |
| **Auth** | ⚠️ 0% | StripeOAuth, SessionContext | 1 day |
| **Hooks & Utils** | ⚠️ 0% | useDatasets, useWebSocket, API client | 2 days |

**Time:** 2 weeks | **Complexity:** High (most work) | **Priority:** 1️⃣ CRITICAL

---

## Gap #4: Real-time Updates (WebSocket)

| Component | Status | Solution |
|-----------|--------|----------|
| Connection manager | ❌ Missing | Add `WebSocketManager` to manage clients |
| WebSocket route | ❌ Missing | Create `/ws/{client_id}` endpoint |
| Event broadcaster | ❌ Missing | Broadcast progress from Prefect tasks |
| Frontend hook | ❌ Missing | `useWebSocket()` hook in Next.js |

**Time:** 2-3 days | **Complexity:** Medium | **Priority:** 2️⃣ IMPORTANT

---

## Gap #5: Email Notifications (SendGrid)

| Feature | Status | Solution |
|---------|--------|----------|
| SendGrid client | ❌ Missing | Add to deps + create `EmailService` |
| Email templates | ❌ Missing | 4 templates (complete, failed, limit, review) |
| Integration | ❌ Missing | Hooks in Prefect tasks + Stripe webhooks |
| Audit logging | ❌ Missing | Log sent emails to database |

**Time:** 1-2 days | **Complexity:** Low | **Priority:** 2️⃣ IMPORTANT

---

## File Structure to Create

```bash
# Backend services
src/
├─ services/
│  ├─ parsers/
│  │  ├─ __init__.py
│  │  ├─ base.py              (AbstractBaseParser)
│  │  ├─ lightweight.py        (CSV, JSON, Excel, PDF)
│  │  ├─ docling.py            (Stub, calls microservice)
│  │  └─ factory.py            (ParserFactory)
│  ├─ storage_service.py       (S3/R2 upload/download)
│  ├─ email_service.py         (SendGrid integration)
│  └─ websocket_manager.py     (Connection management)
├─ core/
│  └─ file_detection.py        (MIME type + complexity)
├─ tasks/
│  └─ cleanup_storage.py       (Retention policy job)
└─ api/v1/
   ├─ storage/
   │  └─ router.py             (Upload/download endpoints)
   └─ ws/
      └─ router.py             (WebSocket endpoint)

# Frontend components
data-foundry/frontend/src/
├─ components/
│  ├─ upload/
│  ├─ processing/
│  ├─ results/
│  └─ auth/
├─ pages/
│  ├─ dashboard/
│  ├─ admin/
│  └─ [auth pages]
├─ lib/
│  ├─ api/
│  ├─ hooks/
│  ├─ types/
│  └─ utils/
└─ styles/
```

---

## Implementation Order (Recommended)

### Phase 1: Parser & Storage (Week 1-2)
1. **Parser abstraction** (3 days)
   - Create base class + implementations
   - File type detection
   - ParserFactory routing

2. **Storage service** (2 days)
   - Add S3/R2 client
   - Upload/download handlers
   - Retention policies

3. **Database updates** (1 day)
   - Add `file_storage` table
   - Migration script

### Phase 2: Frontend (Week 3-4)
1. **Auth setup** (1 day)
   - Stripe OAuth flow
   - Session management

2. **Upload page** (2 days)
   - Drag & drop file input
   - Tier detection
   - Cost estimator

3. **Monitor page** (2 days)
   - Real-time progress (WebSocket)
   - Stage timeline
   - Cost tracker

4. **Results page** (2 days)
   - Results viewer
   - Quality report
   - Export options

### Phase 3: Real-time & Notifications (Week 5)
1. **WebSocket** (2 days)
   - Connection manager
   - Frontend hook
   - Event broadcaster

2. **Email notifications** (1 day)
   - SendGrid integration
   - Email templates

3. **Admin panel UI** (2 days)
   - User management
   - Dataset management
   - Billing history

---

## Dependencies to Add

```toml
# pyproject.toml
boto3>=1.28.0              # AWS S3
botocore>=1.31.0           # AWS SDK core
sendgrid>=6.10.0           # Email service
aiofiles>=23.2.0           # Already present ✅
websockets>=11.0.0         # WebSocket support (if not FastAPI's)
```

```bash
# data-foundry/frontend/
npm install --save \
  shadcn-ui \
  @hookform/react \
  zod \
  @tanstack/react-query \
  next-auth
```

---

## What NOT to Do

❌ **Don't** rebuild the backend—it's excellent
❌ **Don't** change database schema significantly—use JSONB for flexibility
❌ **Don't** add new AI models—you have OpenAI, Anthropic, LiteLLM covered
❌ **Don't** over-engineer file storage—start with S3, add optimization later
❌ **Don't** build custom auth—use Stripe OAuth (already in Stripe SDK)

---

## Decision Points

### Parser Strategy: Lightweight-First vs. All-In

| Approach | Pros | Cons |
|----------|------|------|
| **Lightweight-first** | Smaller footprint, faster startup, cheaper | Docling setup later |
| **All-in** | OCR from day 1 | 4GB RAM overhead, complexity |

**Recommendation:** Lightweight-first. Add Docling in Month 2.

### Storage: AWS S3 vs. Cloudflare R2

| Service | Cost | Features | Recommendation |
|---------|------|----------|-----------------|
| **AWS S3** | ~$0.023/GB | Industry standard, webhooks | ✅ Use for MVP |
| **Cloudflare R2** | $0.015/GB | Cheaper, simpler API | Migrate later |

**Recommendation:** Start with S3, migrate to R2 after MVP if cost-sensitive.

### Email Service: SendGrid vs. Mailgun

| Service | Cost | Reputation | Recommendation |
|---------|------|-----------|-----------------|
| **SendGrid** | $0.10-1/msg | Industry leader, Stripe integration | ✅ Use |
| **Mailgun** | $0.50-1/msg | Developer-friendly | Alternative |

**Recommendation:** SendGrid (simpler Stripe integration).

---

## Quick Win: 1-Day Wins

These can be done in parallel to buy time for bigger features:

- [ ] Add boto3 to dependencies (30 min)
- [ ] Create file type detection module (2 hours)
- [ ] Add SendGrid stub (1 hour)
- [ ] Create parser factory interface (2 hours)

**Total:** ~6 hours of work, unblocks all other features.

---

## Success Criteria for MVP Launch

- [ ] Upload page: File ingestion working
- [ ] Monitor page: Real-time progress visible
- [ ] Results page: CSV/JSON download working
- [ ] Billing: Stripe charges applying correctly
- [ ] Emails: Notifications sending
- [ ] Frontend: Deployed and accessible
- [ ] Docs: README updated with screenshots

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Frontend takes 3+ weeks | High | Start immediately, parallelize backend |
| WebSocket complexity | Medium | Use FastAPI's built-in support, test early |
| S3 costs scale | Low | Implement retention policies from day 1 |
| File detection misses edge cases | Medium | Add manual override in UI |

---

## ROI Analysis: What to Build First

```
Effort (days) vs. Customer Value

🟢 Parser abstraction   (3 days) → Enables all file types    ⭐⭐⭐⭐⭐
🟢 Storage service      (2 days) → Enables file retention    ⭐⭐⭐⭐⭐
🟡 Frontend upload      (2 days) → Customers can upload     ⭐⭐⭐⭐
🟡 Frontend monitor     (2 days) → Customers see progress   ⭐⭐⭐⭐
🟡 Frontend results     (2 days) → Customers download data  ⭐⭐⭐⭐
🔴 WebSocket           (2 days) → Nice-to-have UX          ⭐⭐
🔴 Email notifications (1 day)  → Convenience feature      ⭐⭐
```

**Minimum viable:** Parser + Storage + Upload + Monitor + Results = 11 days

---

## Checklist for Next Sprint

- [ ] Review this analysis with team
- [ ] Decide: Lightweight-first or all-in?
- [ ] Decide: AWS S3 or Cloudflare R2?
- [ ] Create GitHub issues for each gap
- [ ] Assign owners for Phase 1 work
- [ ] Set milestone: "MVP Launch"
- [ ] Start on parser abstraction layer

---

**Last Updated:** 2025-12-28
**Next Review:** After Phase 1 (Parser + Storage)
**Status:** Ready to implement
