# Technology Stack Decisions
## Data Foundry Frontend Architecture

**Decision Date:** December 23, 2025
**Decision Maker:** Solo Developer (Carlos)
**Product Type:** EaaS+LaaS SaaS Product (Enrichment-as-a-Service + Labeling-as-a-Service)

---

## Context

Data Foundry is a **commercial SaaS product** (not an internal tool) that will be sold to customers. The backend is production-ready with 19 REST API endpoints across 6 modules. The frontend needs to support:
- Customer-facing dashboard for data enrichment and labeling workflows
- Marketing pages (landing, pricing, features, documentation)
- SEO optimization for customer acquisition
- Multi-tenant architecture with secure authentication
- Social login and MFA for enterprise customers

---

## Decision 1: Build Tool - Next.js ✅

### Decision
**Use Next.js 14+ with App Router**

### Rationale

**Product Requirements:**
- ✅ **SEO Critical**: Need organic traffic for customer acquisition
- ✅ **Marketing Pages**: Landing page, pricing, features, blog need SSR/SSG
- ✅ **Public-facing Application**: Customer dashboard, not internal admin tool
- ✅ **Future Flexibility**: May add public API docs, blog, changelog
- ✅ **Performance**: SSR provides better initial page loads for customers

**Technical Fit:**
- ✅ **Already Partially Configured**: `.env.local` has `NEXT_PUBLIC_*` variables
- ✅ **VSCode Launch Config**: Next.js debugging already set up
- ✅ **shadcn/ui Compatibility**: Works seamlessly with Next.js
- ✅ **TypeScript Support**: First-class TypeScript integration
- ✅ **API Routes**: Can serve as BFF (Backend-for-Frontend) if needed

**Alternatives Considered:**
- ❌ **Vite + React**: Faster dev experience, but no SSR/SSG for marketing pages
- ❌ **Remix**: Great for data-heavy apps, but smaller ecosystem than Next.js
- ❌ **SvelteKit**: Excellent performance, but smaller talent pool for hiring

### Implementation Details

**Framework:** Next.js 14+ (App Router)
**Routing:** App Router (`app/` directory)
**Data Fetching:** Server Components + TanStack Query for client state
**Styling:** Tailwind CSS + shadcn/ui components
**Deployment:** Vercel (recommended) or Docker containerization

### Migration Notes

**Existing Environment Variables** (`.env.local`):
```bash
# Already configured - no changes needed
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_V1_STR=/api/v1
NEXT_PUBLIC_APP_NAME=Data Foundry
NEXT_PUBLIC_APP_VERSION=1.0.0
```

**Existing Utilities to Migrate:**
```
/frontend/src/lib/
├── api-client.ts      → Migrate to Next.js App Router patterns
├── data-table.ts      → Keep as-is (compatible)
├── font.ts            → Update for next/font
├── format.ts          → Keep as-is (compatible)
├── parsers.ts         → Keep as-is (compatible)
├── searchparams.ts    → Update for useSearchParams from next/navigation
└── utils.ts           → Keep as-is (compatible)
```

---

## Decision 2: Authentication - Clerk ✅

### Decision
**Use Clerk for Authentication & User Management**

### Rationale

**Product Requirements:**
- ✅ **Social Login**: Google, GitHub, LinkedIn for faster onboarding
- ✅ **MFA**: Required for enterprise customers and compliance
- ✅ **User Management Dashboard**: Customer support needs to manage users
- ✅ **Email Verification**: Reduce spam signups
- ✅ **Password Resets**: Self-service for customers
- ✅ **Session Management**: Secure session handling with refresh tokens
- ✅ **Development Speed**: Auth working in hours, not weeks

**Business Considerations:**
- ✅ **Time to Market**: Focus development time on core product (data enrichment/labeling)
- ✅ **Cost**: Free tier: 10,000 MAU, Production: ~$25/month for 1000 MAU (negligible vs dev time)
- ✅ **Maintenance**: No auth infrastructure to maintain, patch, or secure
- ✅ **Compliance**: Clerk handles GDPR, SOC 2, password security standards
- ✅ **Already Configured**: Credentials in `.env.local` - ready to use

**Technical Integration:**
- ✅ **Next.js First-class Support**: `@clerk/nextjs` package with App Router support
- ✅ **Backend Compatibility**: FastAPI can validate Clerk JWTs using existing `src/core/security.py`
- ✅ **Multi-tenant Architecture**: Clerk Organizations map to your tenant model
- ✅ **API Protection**: Middleware for protecting routes
- ✅ **Webhooks**: Sync user data to PostgreSQL via Clerk webhooks

**Alternatives Considered:**
- ❌ **Custom JWT**: Full control but 2-4 weeks development time for OAuth, MFA, password resets, email verification, user dashboard
- ❌ **Auth0**: Similar to Clerk but more expensive and complex configuration
- ❌ **Supabase Auth**: Great option but less Next.js-focused than Clerk
- ❌ **NextAuth.js**: Open-source but requires more manual configuration for social providers and MFA

### Implementation Details

**Authentication Flow:**
```
1. User signs in via Clerk (Next.js frontend)
   ↓
2. Clerk generates JWT with user metadata
   ↓
3. Next.js sends JWT in Authorization header to FastAPI
   ↓
4. FastAPI validates JWT signature using Clerk's public key (src/core/security.py)
   ↓
5. FastAPI extracts user_id and tenant_id from JWT claims
   ↓
6. FastAPI enforces Row-Level Security (RLS) based on tenant_id
```

**Backend Integration (FastAPI):**
```python
# src/core/security.py (update existing JWT validation)

from jose import jwt, JWTError
import httpx

CLERK_PEM_PUBLIC_KEY_URL = "https://api.clerk.dev/v1/jwks"

async def get_current_user_token(token: str = Depends(oauth2_scheme)):
    """Validate Clerk JWT and extract user/tenant info"""
    try:
        # Fetch Clerk's public key
        async with httpx.AsyncClient() as client:
            jwks = await client.get(CLERK_PEM_PUBLIC_KEY_URL)
            # Validate JWT signature using Clerk's public key
            payload = jwt.decode(
                token,
                jwks.json(),
                algorithms=["RS256"],
                audience="fastapi"  # Configure in Clerk dashboard
            )

            # Extract user/tenant from Clerk metadata
            user_id = payload.get("sub")
            tenant_id = payload.get("org_id")  # Clerk organization ID

            return {"user_id": user_id, "tenant_id": tenant_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

**Frontend Components:**
```typescript
// app/layout.tsx
import { ClerkProvider } from '@clerk/nextjs'

export default function RootLayout({ children }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  )
}

// app/dashboard/page.tsx (protected route)
import { auth } from '@clerk/nextjs'
import { redirect } from 'next/navigation'

export default async function DashboardPage() {
  const { userId } = auth()
  if (!userId) redirect('/sign-in')

  // Fetch user's data from FastAPI with Clerk JWT
  return <Dashboard />
}
```

**Clerk Configuration:**
- Enable Google, GitHub OAuth providers
- Enable MFA (TOTP and SMS)
- Configure Organizations for multi-tenancy
- Set up webhooks for user sync to PostgreSQL
- Configure JWT template with custom claims (tenant_id, role)

### Cost Analysis

**Clerk Pricing:**
- Free: Up to 10,000 Monthly Active Users (MAU)
- Pro: $25/month for 1,000 MAU, then $0.02/MAU
- Enterprise: Custom pricing for >100k MAU

**Custom Auth Alternative Cost:**
- Development: 2-4 weeks × $100/hour = $8,000-$16,000
- Maintenance: Ongoing security patches, OAuth provider updates
- Infrastructure: Email service (SendGrid/Mailgun), SMS for MFA
- **Total**: $8,000+ upfront + $50-100/month ongoing

**Decision:** Clerk saves 2-4 weeks of development time. At $100/hour solo dev rate, that's $8,000-$16,000 in value. Even at $25/month for 1,000 users, Clerk pays for itself in the first month.

---

## Decision 3: UI Framework - shadcn/ui ✅

### Decision
**Use shadcn/ui with Tailwind CSS**

### Rationale
- ✅ **Copy-paste components**: No npm dependency bloat
- ✅ **Full customization**: Own the code, modify as needed
- ✅ **Next.js Optimized**: Built for App Router
- ✅ **TypeScript-first**: Excellent type safety
- ✅ **Accessible**: ARIA compliance built-in (Radix UI primitives)
- ✅ **Production-ready**: Used by Vercel, Linear, Cal.com

**Components for Data Foundry:**
- Dashboard layouts (sidebar, header)
- Data tables (quality validation results)
- Forms (A/B test creation, signal detection config)
- Charts (metrics visualization)
- Dialogs (pipeline trigger confirmations)
- Toast notifications (API success/error messages)

---

## Decision 4: API Client Generation - Orval ✅

### Decision
**Use Orval for TypeScript API Client Generation**

### Rationale
- ✅ **OpenAPI-native**: Generates from `/openapi.json`
- ✅ **React Query Integration**: Auto-generates TanStack Query hooks
- ✅ **Type Safety**: End-to-end type safety from FastAPI to Next.js
- ✅ **Automatic Updates**: Regenerate on API changes
- ✅ **Next.js Compatible**: Works with App Router and Server Components

**Alternative Considered:**
- ❌ **openapi-generator**: More mature but less React-focused
- ❌ **Manual fetch calls**: Error-prone, no type safety

**Configuration (`orval.config.ts`):**
```typescript
export default {
  'data-foundry-api': {
    input: 'http://localhost:8000/openapi.json',
    output: {
      target: './src/services/api/generated.ts',
      client: 'react-query',
      mode: 'tags-split',
      override: {
        mutator: {
          path: './src/services/api/mutator.ts',
          name: 'customFetch',
        },
      },
    },
  },
}
```

---

## Final Technology Stack Summary

| Category | Technology | Reasoning |
|----------|-----------|-----------|
| **Framework** | Next.js 14+ (App Router) | SSR/SSG for SEO, marketing pages, public-facing SaaS |
| **Language** | TypeScript (strict mode) | Type safety across frontend and API client |
| **UI Components** | shadcn/ui + Radix UI | Copy-paste, customizable, accessible components |
| **Styling** | Tailwind CSS | Utility-first, fast styling, Next.js optimized |
| **Authentication** | Clerk | Managed auth with social login, MFA, user dashboard |
| **API Client** | Orval (OpenAPI → TypeScript) | Auto-generated type-safe API client with React Query |
| **Data Fetching** | TanStack Query (React Query) | Server state management, caching, mutations |
| **Forms** | React Hook Form + Zod | Type-safe forms with validation |
| **Charts** | Recharts or shadcn/charts | Data visualization for metrics, A/B tests |
| **Testing** | Vitest (unit) + Playwright (E2E) | Fast testing aligned with Vite/Next.js |
| **Deployment** | Vercel (recommended) | Zero-config Next.js hosting with edge functions |
| **Package Manager** | npm (standard) | Compatibility with existing `.env.local` setup |

---

## Next Steps (Week 1 Updated)

### Day 1: Project Initialization ✅ (TODAY)
- [x] Technology stack decisions finalized
- [ ] Initialize Next.js project
- [ ] Migrate existing utilities to Next.js structure
- [ ] Configure Clerk authentication

### Day 2: Development Environment
- [ ] Install dependencies (shadcn/ui, TanStack Query, Orval)
- [ ] Configure Orval for API client generation
- [ ] Set up Tailwind CSS and design tokens
- [ ] Create basic layout structure (app router)

### Day 3: Authentication Integration
- [ ] Implement Clerk sign-in/sign-up pages
- [ ] Configure protected routes middleware
- [ ] Update FastAPI JWT validation for Clerk tokens
- [ ] Test end-to-end auth flow

### Day 4-5: User Flow Analysis
- [ ] Create user journey maps (3 personas)
- [ ] Document 5 primary workflows with diagrams
- [ ] Create wireframes for key screens
- [ ] Document in `/docs/planning/USER_FLOWS.md`

### Weekend: Core Components
- [ ] Dashboard layout (sidebar, header, content area)
- [ ] Navigation menu
- [ ] API client integration (fetch health endpoint)
- [ ] Toast notification system

---

## Approval Status

- [x] **Decision 1 (Next.js):** ✅ APPROVED - SaaS product needs SSR/SEO
- [x] **Decision 2 (Clerk):** ✅ APPROVED - Speed to market, social login, MFA
- [x] **Decision 3 (shadcn/ui):** ✅ APPROVED - Production-ready components
- [x] **Decision 4 (Orval):** ✅ APPROVED - Type-safe API client

**Ready to Proceed:** YES ✅

---

**Document Version:** 1.0
**Last Updated:** December 23, 2025
**Next Review:** After MVP completion (Week 4)
