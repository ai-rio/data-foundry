# Frontend Strategy: Managed Data Outcomes (MDO) Positioning
## Data Foundry SaaS Architecture Aligned with Market Validation

**Created:** December 24, 2025
**Context:** Partner AI strategic reframe from "LaaS/EaaS" to "Managed Data Outcomes"
**Reference:** `/docs/architecture/data-foundry.md` (Project Brief)

---

## Executive Summary

Data Foundry is **NOT** competing with Scale AI/Labelbox (tools) or BPO firms (labor).
We're creating a **new category: Managed Data Outcomes (MDO)**.

**We sell:** "Clean, audit-ready data by 8 AM tomorrow"
**Not:** "Access to our labeling platform"

This positioning fundamentally changes what the frontend must accomplish.

---

## The Strategic North Star (From Partner AI)

### Traditional LaaS Positioning (WRONG):
> "Self-service data labeling platform with AI assistance"
> **Problem:** Competing on features against Scale AI ($7.3B valuation)

### Managed Data Outcomes Positioning (RIGHT):
> "Send messy data, get ML-ready datasets by morning"
> **Advantage:** Competing on outcomes, not features

### What This Means for Frontend:

| Traditional SaaS UI | MDO-Focused UI |
|---------------------|----------------|
| Complex dashboard with 20+ features | Simple upload → process → download flow |
| Onboarding tutorial (30 min) | Works in 5 minutes |
| "Configure your labeling pipeline" | "We handle everything" |
| Feature comparison tables | Outcome guarantee badges |
| Per-seat pricing | Per-outcome pricing |

**Key Insight:** The frontend should feel like **FedEx for data** (drop it off, pick it up clean), NOT like **Photoshop** (100 tools to master).

---

## Frontend User Journeys (MDO-Aligned)

### Primary Journey: "The Overnight Pipeline"

**Persona:** Data Scientist at Series A healthtech startup

**Current Pain:**
- Downloads 10k patient records from EHR
- Spends 2 weeks cleaning + labeling manually
- Misses ML model deployment deadline

**Data Foundry Solution:**
1. **7 PM Monday:** Upload CSV to Data Foundry
2. **8 AM Tuesday:** Download labeled, PII-scrubbed dataset
3. **9 AM Tuesday:** Train ML model with clean data

**Frontend Pages Needed:**
```
Landing Page → Upload Page → Processing Dashboard → Download Results
      ↓              ↓                ↓                    ↓
   SEO/Social    Drag-drop     Real-time progress    Audit report
   optimized     CSV upload    (confidence metrics)   + download
```

**NOT Needed (Yet):**
- ❌ Advanced pipeline builder
- ❌ Custom model training UI
- ❌ Collaboration features
- ❌ API playground (customers don't care about API, they want outcomes)

---

## Page Hierarchy (Outcome-First)

### Public Pages (SEO + Conversion Focused)

**1. Landing Page** (`/`)
- **Headline:** "Send Messy Data, Get ML-Ready Datasets by Morning"
- **Subhead:** "70% cheaper than Scale AI. HIPAA-compliant. No engineering required."
- **CTA:** "Upload Your First Dataset" (not "Start Free Trial")
- **Social Proof:** "Healthcare AI teams at [Company A], [Company B] trust Data Foundry"
- **Demo Video:** "The Confidence Switch" (2 min embedded)

**2. Pricing Page** (`/pricing`)
- **NOT:** Feature comparison table
- **IS:** Outcome-based tiers:
  ```
  Bronze Tier: $0.12/label (85% AI confidence, 15% human review)
  → Use case: E-commerce product categorization

  Silver Tier: $0.10/label (90% AI confidence, 8% human review)
  → Use case: Financial document classification

  Gold Tier: $0.08/label (95% AI confidence, 3% human review)
  → Use case: HIPAA-compliant healthcare labeling
  ```
- **Calculator:** "10,000 records × Gold tier = $800 (vs. $2,800 with Scale AI)"

**3. Use Cases Page** (`/use-cases`)
- Healthcare: "HIPAA-Compliant Medical Record Labeling"
- Finance: "KYC Document Classification with Audit Trails"
- E-commerce: "Product Categorization at Scale"

**4. Integration Partners** (`/integrations`)
- dbt Cloud: "Add enrichment to your transformation pipeline"
- Fivetran/Airbyte: "Enrich data after ingestion"
- Label Studio: "Human review for edge cases"

**5. How It Works** (`/how-it-works`)
- Step 1: Upload your dataset (CSV, JSON, Parquet)
- Step 2: We scrub PII/PHI automatically (Presidio)
- Step 3: AI labels with confidence routing (GPT-4o → Human)
- Step 4: Download audit-ready results in 8 hours

### Application Pages (Customer Portal)

**6. Upload Dashboard** (`/dashboard/upload`)
- Drag-drop CSV upload
- Auto-detect columns for labeling
- PII detection preview: "We found 3 columns with potential PII (SSN, phone, email)"
- Pricing estimate: "10,000 records × Gold tier = $800"
- "Process Now" button

**7. Jobs Dashboard** (`/dashboard/jobs`)
- Active jobs: Real-time progress (15% complete, 1,500/10,000 labeled)
- Confidence metrics: "85% AI-only, 12% human review, 3% rejected"
- Completed jobs: Download CSV + audit report

**8. Results Page** (`/dashboard/results/[job_id]`)
- Download labeled dataset (CSV)
- Download audit report (PDF):
  - Provenance metadata (which model, confidence scores)
  - PII redaction log
  - Human review notes
- View sample labeled records (first 100)

**9. Billing Dashboard** (`/dashboard/billing`)
- **NOT:** "You used 1,234 API calls"
- **IS:** "You processed 10,000 records this month:"
  - 8,500 AI-labeled ($0.08 each) = $680
  - 1,200 human-reviewed ($0.10 each) = $120
  - 300 rejected (no charge) = $0
  - **Total: $800** (vs. $2,800 with Scale AI)

---

## A/B Testing Strategy (Week 1-2)

### Test: SaaS Mode vs. Service Mode

**Version A: SaaS Positioning**
- Headline: "Self-Service Data Labeling Platform"
- CTA: "Start Labeling in 5 Minutes"
- Pricing: "$0.08/label + $99/month platform fee"
- Value prop: "Control your labeling pipeline"

**Version B: Managed Service Positioning**
- Headline: "Send Messy Data, Get ML-Ready Datasets by Morning"
- CTA: "Upload Your First Dataset"
- Pricing: "$0.12/label, all-inclusive (no platform fee)"
- Value prop: "We handle everything—you just upload and download"

**Metrics to Track:**
| Metric | Version A | Version B | Hypothesis |
|--------|-----------|-----------|------------|
| Bounce rate | ? | ? | B will have lower bounce |
| Time to CTA click | ? | ? | B will be faster (simpler) |
| Demo requests | ? | ? | B will convert better |
| "Pricing too high" feedback | ? | ? | A will get more pushback |

**Next.js Implementation:**
```typescript
// app/page.tsx (landing page with A/B test)
import { headers } from 'next/headers'

export default async function LandingPage() {
  const headersList = headers()
  const variant = headersList.get('x-vercel-variant') || 'b'

  return variant === 'a'
    ? <SaaS_PositioningLanding />
    : <ManagedService_PositioningLanding />
}
```

---

## Tech Stack Decisions: How They Support MDO

### ✅ Next.js 14+ (App Router)

**Why it's perfect for MDO validation:**
1. **Landing page A/B testing:** Deploy variant B on Vercel edge
2. **SEO:** Rank for "HIPAA-compliant data labeling" (acquisition channel)
3. **Marketing pages:** Pricing, use cases, integrations (educate buyers)
4. **Demo video embed:** Fast load times, optimized images
5. **Server actions:** "Upload CSV" can be a server action (no API boilerplate)

**NOT using it for:**
- ❌ Complex SPA interactions (we're not building Figma)
- ❌ Real-time collaboration (not needed for batch processing)

### ✅ Clerk Authentication

**Why it's perfect for MDO validation:**
1. **Fast prospect onboarding:** "Sign in with Google" → upload dataset in 30 seconds
2. **Multi-tenant isolation:** Clerk Organization ID → PostgreSQL RLS tenant_id
3. **User management:** When you get first 10 customers, manage them in Clerk dashboard
4. **Compliance:** Clerk is SOC 2 compliant (critical for healthcare/finance)

**Integration with FastAPI:**
```python
# src/core/security.py (validate Clerk JWTs)
from jose import jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = jwt.decode(token, CLERK_PUBLIC_KEY, algorithms=["RS256"])
    tenant_id = payload.get("org_id")  # Clerk organization ID
    user_id = payload.get("sub")
    return {"user_id": user_id, "tenant_id": tenant_id}
```

### ✅ shadcn/ui

**Why it's perfect for MDO:**
1. **Simple, clean UI:** Customers want "upload → download," not feature overload
2. **Fast customization:** Copy-paste components, modify for brand
3. **Production-ready:** Companies like Vercel/Cal.com use it (credibility)

**Key Components for MDO:**
- Upload: File dropzone with drag-drop
- Processing: Progress bar with confidence metrics
- Results: Data table with download button
- Pricing: Tiered pricing cards with calculator

### ✅ Orval (Auto-generated API Client)

**Why it's critical for MDO:**
1. **Type safety:** Backend changes (confidence routing tweaks) auto-update frontend
2. **React Query hooks:** Auto-generated `useUploadDataset()`, `useGetJobStatus()`
3. **No manual API coding:** Focus on UX, not fetch() boilerplate

**Example:**
```typescript
// Generated by Orval from OpenAPI spec
import { useUploadDataset } from '@/services/api/generated'

export function UploadForm() {
  const { mutate: uploadDataset, isLoading } = useUploadDataset()

  const handleUpload = (file: File) => {
    uploadDataset({ file }, {
      onSuccess: (data) => {
        router.push(`/dashboard/jobs/${data.job_id}`)
      }
    })
  }

  return <FileDropzone onDrop={handleUpload} loading={isLoading} />
}
```

---

## Week 1 Action Plan: Aligned with Partner AI Strategy

### Monday: Technical Foundation + Demo Video

**Morning (Technical):**
- [ ] Initialize Next.js project: `npx create-next-app@latest frontend`
- [ ] Configure Clerk: Add `CLERK_SECRET_KEY` to Next.js `.env.local`
- [ ] Test FastAPI → Clerk JWT validation (update `src/core/security.py`)

**Afternoon (Content):**
- [ ] Record "Confidence Switch" demo video (2 min):
  - Upload messy healthcare CSV
  - Show PII redaction
  - Show confidence routing (85% AI, 15% human)
  - Download audit-ready results
- [ ] Upload video to Loom/YouTube (unlisted)

**Evening (Setup):**
- [ ] Install shadcn/ui: `npx shadcn@latest init`
- [ ] Create basic layout: Header, Footer, Container

---

### Tuesday: Landing Pages (A/B Test)

**Morning (Version A: SaaS Positioning):**
- [ ] Create `/app/page-saas.tsx`:
  - Headline: "Self-Service Data Labeling Platform"
  - Feature list (AI labeling, human review, API access)
  - CTA: "Start Free Trial"
  - Pricing: "$0.08/label + $99/month"

**Afternoon (Version B: Managed Service Positioning):**
- [ ] Create `/app/page.tsx`:
  - Headline: "Send Messy Data, Get ML-Ready Datasets by Morning"
  - Outcome-focused copy (8-hour turnaround, HIPAA-compliant)
  - Embedded demo video
  - CTA: "Upload Your First Dataset"
  - Pricing: "$0.12/label, all-inclusive"

**Evening (Analytics):**
- [ ] Add Vercel Analytics
- [ ] Set up A/B test: 50% traffic to each variant
- [ ] Add event tracking: CTA clicks, video plays, scroll depth

---

### Wednesday: Outreach + API Integration

**Morning (Orval Setup):**
- [ ] Install Orval: `npm install -D orval`
- [ ] Create `orval.config.ts`:
  ```typescript
  export default {
    'data-foundry': {
      input: 'http://localhost:8000/openapi.json',
      output: {
        target: './src/services/api/generated.ts',
        client: 'react-query',
      },
    },
  }
  ```
- [ ] Generate API client: `npx orval`

**Afternoon (Cold Emails):**
- [ ] Draft "Managed Outcome" email template
- [ ] Research 50 prospects:
  - VP/Head of Data at Series A-B healthtech
  - Data Science Managers at fintech (fraud, credit)
  - ML Engineers at e-commerce (product categorization)
- [ ] Send 25 emails (personalized)

**Evening (Content):**
- [ ] Post demo video on Twitter/LinkedIn
- [ ] Write "Why AI Labeling Needs a Confidence Switch" blog post (draft)

---

### Thursday: Upload Flow + Pricing Page

**Morning (Upload Page):**
- [ ] Create `/app/dashboard/upload/page.tsx`:
  - File dropzone (shadcn/ui)
  - CSV preview (first 5 rows)
  - PII detection warning
  - Pricing estimate
  - "Process Now" button → calls `useUploadDataset()`

**Afternoon (Pricing Page):**
- [ ] Create `/app/pricing/page.tsx`:
  - Tiered pricing cards (Bronze/Silver/Gold)
  - Pricing calculator: Input # of records, see cost
  - Comparison table: Data Foundry vs. Scale AI
  - CTA: "Upload Your First Dataset"

**Evening (Integration Partner Emails):**
- [ ] Draft partnership emails for:
  - dbt Cloud
  - Fivetran/Airbyte
  - Label Studio
- [ ] Send to partnerships@[company].com

---

### Friday: Jobs Dashboard + Margin Analysis

**Morning (Jobs Dashboard):**
- [ ] Create `/app/dashboard/jobs/page.tsx`:
  - Active jobs table (job_id, status, progress %)
  - Completed jobs with download button
  - Real-time updates using React Query polling

**Afternoon (Margin Test):**
- [ ] Run cost analysis on 1,000 test records:
  - Track actual OpenAI API costs
  - Simulate human review costs ($2/label for 3%)
  - Calculate margins for each tier (Bronze/Silver/Gold)
- [ ] Adjust pricing if margins < 50%

**Evening (Validation Interviews):**
- [ ] Review demo requests from cold emails
- [ ] Book 3+ validation interviews for next week
- [ ] Prepare 15-question interview script

---

### Weekend: Polish + HackerNews Launch

**Saturday:**
- [ ] Complete blog post: "Why AI Labeling Needs a Confidence Switch"
- [ ] Add use cases page: `/app/use-cases/page.tsx`
- [ ] Add "How It Works" page: `/app/how-it-works/page.tsx`

**Sunday:**
- [ ] Submit blog post to HackerNews (Show HN)
- [ ] Post on r/MachineLearning, r/DataScience
- [ ] Monitor landing page A/B test results
- [ ] Analyze: Which variant has better conversion?

---

## Success Metrics (Week 1)

**Technical:**
- [ ] ✅ Next.js app deployed to Vercel
- [ ] ✅ Clerk auth working (sign-up → upload flow)
- [ ] ✅ Orval API client auto-generated
- [ ] ✅ FastAPI validates Clerk JWTs

**Validation:**
- [ ] ✅ 3+ booked demos with qualified prospects
- [ ] ✅ 50+ landing page visitors (from emails + social)
- [ ] ✅ A/B test shows clear winner (Version B expected)
- [ ] ✅ 1+ customer willing to test with real data

**Business:**
- [ ] ✅ Margin analysis proves $0.08-0.12/label is profitable
- [ ] ✅ Clear preference for Managed Service (Version B) vs. SaaS (Version A)
- [ ] ✅ First partnership conversation booked (dbt/Fivetran/Label Studio)

**If you DON'T have these by Friday:**
- 🚨 **<3 demos booked:** Wrong ICP or messaging (refine cold emails)
- 🚨 **Version A wins A/B test:** Market wants DIY tools, not managed service (pivot positioning)
- 🚨 **Margins <50%:** Pricing too low or human review % too high (adjust confidence thresholds)

---

## The Critical Integration Test (Before Talking to Customers)

### FastAPI → Clerk JWT Validation

**Test this end-to-end flow:**

1. **User signs in via Clerk (Next.js):**
   ```typescript
   // app/sign-in/page.tsx
   import { SignIn } from '@clerk/nextjs'
   export default function SignInPage() {
     return <SignIn redirectUrl="/dashboard/upload" />
   }
   ```

2. **Next.js sends Clerk JWT to FastAPI:**
   ```typescript
   // src/services/api/mutator.ts (Orval custom fetch)
   import { auth } from '@clerk/nextjs'

   export async function customFetch(url: string, options: RequestInit) {
     const { getToken } = auth()
     const token = await getToken()

     return fetch(url, {
       ...options,
       headers: {
         ...options.headers,
         Authorization: `Bearer ${token}`,
       },
     })
   }
   ```

3. **FastAPI validates JWT and extracts tenant_id:**
   ```python
   # src/core/security.py
   from jose import jwt
   import httpx

   CLERK_JWKS_URL = "https://[your-clerk-domain]/.well-known/jwks.json"

   async def get_current_user(token: str = Depends(oauth2_scheme)):
       async with httpx.AsyncClient() as client:
           jwks = await client.get(CLERK_JWKS_URL)
           payload = jwt.decode(token, jwks.json(), algorithms=["RS256"])

       tenant_id = payload.get("org_id")  # Clerk organization ID
       user_id = payload.get("sub")

       if not tenant_id:
           raise HTTPException(status_code=403, detail="No organization selected")

       return {"user_id": user_id, "tenant_id": tenant_id}
   ```

4. **PostgreSQL RLS enforces tenant isolation:**
   ```sql
   -- Already implemented in your backend
   CREATE POLICY tenant_isolation ON data_records
   USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
   ```

**Integration Test:**
```bash
# Start FastAPI
cd data-foundry
uvicorn src.main:app --reload

# Start Next.js
cd frontend
npm run dev

# Test flow:
1. Sign in via Clerk (http://localhost:3000/sign-in)
2. Upload CSV (http://localhost:3000/dashboard/upload)
3. Verify FastAPI receives JWT and extracts tenant_id
4. Verify PostgreSQL RLS blocks cross-tenant queries
```

**If any step fails, STOP and fix before customer demos.**

---

## Why This Strategy Wins

**Your partner AI nailed it:**

1. **You're not competing on features** (Scale AI has more)
2. **You're competing on outcomes** ("8 hours, $800, audit-ready")
3. **You've already built it** (most founders waste months validating vapor)

**The frontend's job:**
- ✅ Make the outcome VISIBLE (demo video, confidence metrics)
- ✅ Make signup FRICTIONLESS (Clerk social login)
- ✅ Make pricing TRANSPARENT (tiered outcome pricing)
- ✅ Make validation FAST (A/B test SaaS vs. Managed Service in Week 1)

**Go get your first paying customer this week.**

---

**Document Version:** 1.0
**Last Updated:** December 24, 2025
**Next Review:** After Week 1 validation results
