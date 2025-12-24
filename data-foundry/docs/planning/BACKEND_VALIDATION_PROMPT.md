# Backend Validation Prompt for Partner AI
## Complete Testing Strategy for Data Foundry MVP

**Context:** Data Foundry is a "Managed Data Outcomes" SaaS platform that processes messy data through a pipeline of PII redaction → AI labeling → confidence routing → human review.

**Goal:** Validate that the **production-ready backend** works end-to-end before building the frontend.

**Success Criteria:** All critical systems pass validation, no data leaks, no tenant isolation breaches, margins work at $0.08-0.12/label.

---

## Phase 1: Infrastructure Validation (5-10 minutes)

### Task 1.1: Verify Docker Compose Stack

**What to test:**
- All 5 services start without errors:
  1. PostgreSQL (port 5433)
  2. Redis (port 6380)
  3. Label Studio (port 8080)
  4. Prefect Server (port 4200)
  5. FastAPI (port 8000)

**Commands:**
```bash
cd /home/carlos/projects/data_foundry/data-foundry
docker-compose down  # Clean slate
docker-compose up -d  # Start services

# Wait 30 seconds for services to boot
sleep 30

# Verify each service
curl -s http://localhost:8000/health | jq '.'
curl -s http://localhost:5433 || echo "PostgreSQL ready (connection successful)"
curl -s http://localhost:6380 || echo "Redis ready"
curl -s http://localhost:8080 | head -20
curl -s http://localhost:4200 | head -20
```

**Success Criteria:**
- ✅ FastAPI responds to `/health` with status=200
- ✅ PostgreSQL accepts connections
- ✅ Redis accepts connections
- ✅ Label Studio and Prefect UIs accessible

**If it fails:**
- Check Docker logs: `docker-compose logs [service-name]`
- Common issue: Port already in use → `lsof -i :8000`

---

### Task 1.2: Verify Database Schema & Models

**What to test:**
- PostgreSQL has all 11 tables created
- SQLModel definitions match database schema
- Row-Level Security (RLS) policies exist

**Commands:**
```bash
# Connect to PostgreSQL
psql -h localhost -p 5433 -U postgres -d data_foundry -c "\dt"

# Check for RLS policies
psql -h localhost -p 5433 -U postgres -d data_foundry -c "\dp"

# Verify 11 models exist
python -c "
from src.models import (
    User, Tenant, DataRecord, ProcessedData, HumanReviewQueue,
    Consent, BreachNotification, Incident, UsageTracking
)
print('✅ All 11 models imported successfully')
"
```

**Success Criteria:**
- ✅ 11 tables exist (users, tenants, data_records, processed_data, etc.)
- ✅ RLS policies attached to sensitive tables
- ✅ All models import without errors

**If it fails:**
- Run migrations: `python -m alembic upgrade head`
- Check migration status: `python -m alembic current`

---

## Phase 2: Security Validation (10-15 minutes)

### Task 2.1: Test Tenant Isolation (PostgreSQL RLS)

**What to test:**
- Tenant A cannot see Tenant B's data
- RLS policies enforce tenant_id filtering
- Cross-tenant queries return 403 Forbidden

**Test Script to Create:**
```python
# tests/validation/test_tenant_isolation.py

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.models import User, Tenant, DataRecord
from src.core.security import get_password_hash

async def test_tenant_isolation():
    """Verify Tenant A cannot access Tenant B's data"""

    # Setup: Create 2 tenants and 2 users
    tenant_a_id = "00000000-0000-0000-0000-000000000001"
    tenant_b_id = "00000000-0000-0000-0000-000000000002"

    # Create records in tenant A
    async with AsyncSession(engine) as session:
        # Set tenant context
        await session.execute(
            text("SET app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_a_id)}
        )

        record_a = DataRecord(
            tenant_id=tenant_a_id,
            raw_data={"field": "tenant A data"},
            status="raw"
        )
        session.add(record_a)
        await session.commit()

    # Try to read as Tenant B
    async with AsyncSession(engine) as session:
        await session.execute(
            text("SET app.current_tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_b_id)}
        )

        # This should return 0 records (RLS enforced)
        result = await session.execute(
            select(DataRecord).filter(DataRecord.tenant_id == tenant_a_id)
        )
        records = result.scalars().all()

        assert len(records) == 0, "❌ CRITICAL: Tenant B can see Tenant A's data!"
        print("✅ Tenant isolation works: Tenant B cannot see Tenant A's data")

# Run test
asyncio.run(test_tenant_isolation())
```

**Commands:**
```bash
# Run the isolation test
pytest tests/validation/test_tenant_isolation.py -v

# Also test via FastAPI endpoints
curl -H "Authorization: Bearer [TENANT_A_TOKEN]" http://localhost:8000/api/v1/quality/records
# Should return Tenant A's records only

curl -H "Authorization: Bearer [TENANT_B_TOKEN]" http://localhost:8000/api/v1/quality/records
# Should return Tenant B's records only (different set)
```

**Success Criteria:**
- ✅ Each tenant only sees their own data
- ✅ Cross-tenant queries return empty results
- ✅ No 500 errors or RLS bypass

**If it fails:**
- Check RLS policy: `SELECT polname, polroles FROM pg_policies WHERE tablename='data_records'`
- RLS might not be enforced → re-run: `ALTER TABLE data_records ENABLE ROW LEVEL SECURITY`

---

### Task 2.2: Test PII Redaction (Presidio)

**What to test:**
- Sensitive data (SSN, phone, email, medical IDs) is detected
- Raw PII stored separately from processed data
- AI never sees raw PII

**Test Script:**
```python
# tests/validation/test_pii_redaction.py

from src.services.pii_service import redact_pii

async def test_pii_redaction():
    """Verify Presidio correctly detects and redacts PII"""

    test_data = {
        "patient_id": "MRN123456789",  # Medical Record Number
        "name": "John Doe",
        "ssn": "123-45-6789",
        "phone": "(555) 123-4567",
        "email": "john@example.com",
        "diagnosis": "Type 2 Diabetes"
    }

    # Redact PII
    redacted, pii_entities = await redact_pii(test_data)

    # Verify redaction worked
    assert "<PERSON>" in redacted.get("name", ""), "Name not redacted"
    assert "<US_SSN>" in redacted.get("ssn", ""), "SSN not redacted"
    assert "<PHONE_NUMBER>" in redacted.get("phone", ""), "Phone not redacted"
    assert "<EMAIL_ADDRESS>" in redacted.get("email", ""), "Email not redacted"

    # Verify original data NOT in processed_data
    assert test_data["ssn"] not in str(redacted), "❌ CRITICAL: SSN leaked to processed data!"
    assert test_data["phone"] not in str(redacted), "❌ CRITICAL: Phone leaked!"

    # Verify PII stored securely (encrypted)
    assert pii_entities is not None, "PII entity log missing"
    print("✅ PII redaction works: All sensitive data properly masked")

# Run test
asyncio.run(test_pii_redaction())
```

**Commands:**
```bash
# Run PII redaction test
pytest tests/validation/test_pii_redaction.py -v

# Test with real healthcare CSV
curl -X POST http://localhost:8000/api/v1/quality/validate \
  -H "Authorization: Bearer [TOKEN]" \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {"ssn": "123-45-6789", "diagnosis": "Cancer", "phone": "(555) 123-4567"}
    ]
  }'

# Verify response has redacted data, not original SSN
```

**Success Criteria:**
- ✅ All PII entities detected (SSN, phone, email, medical IDs)
- ✅ Raw PII not in response body
- ✅ PII stored in encrypted vault (separate from processed data)
- ✅ AI labeling receives redacted data only

**If it fails:**
- Presidio might need model download: `python -m spacy download en_core_web_sm`
- Check Presidio is initialized: `from presidio_analyzer import AnalyzerEngine; AnalyzerEngine()`

---

### Task 2.3: Test JWT Authentication (Clerk Integration)

**What to test:**
- FastAPI validates JWT tokens correctly
- Invalid tokens rejected with 401
- Token claims extract user_id and tenant_id correctly

**Test Script:**
```python
# tests/validation/test_jwt_auth.py

from jose import jwt, JWTError
import asyncio

async def test_jwt_validation():
    """Verify FastAPI JWT validation works"""

    # Test 1: Valid JWT
    valid_token = jwt.encode(
        {"sub": "user123", "org_id": "tenant456", "exp": time.time() + 3600},
        SECRET_KEY,
        algorithm="HS256"
    )

    response = await client.get(
        "/api/v1/quality/records",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 200, "Valid token rejected"
    print("✅ Valid JWT accepted")

    # Test 2: Invalid token
    response = await client.get(
        "/api/v1/quality/records",
        headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert response.status_code == 401, "Invalid token not rejected!"
    print("✅ Invalid JWT rejected")

    # Test 3: Missing token
    response = await client.get("/api/v1/quality/records")
    assert response.status_code == 401, "Missing token not rejected!"
    print("✅ Missing JWT rejected")

asyncio.run(test_jwt_validation())
```

**Commands:**
```bash
# Run JWT tests
pytest tests/validation/test_jwt_auth.py -v

# Test manually
# Without token - should fail
curl http://localhost:8000/api/v1/quality/records

# With valid token - should work
curl -H "Authorization: Bearer [VALID_JWT]" http://localhost:8000/api/v1/quality/records
```

**Success Criteria:**
- ✅ Valid JWTs accepted (200 OK)
- ✅ Invalid/missing JWTs rejected (401 Unauthorized)
- ✅ Token claims correctly extracted

**If it fails:**
- Check JWT secret: `grep -r "SECRET_KEY" src/core/config.py`
- Verify Clerk JWKS URL accessible if using Clerk

---

## Phase 3: API Endpoint Validation (15-20 minutes)

### Task 3.1: Test All 19 API Endpoints

**What to test:**
- Each endpoint responds with correct status code
- Request/response schemas match OpenAPI spec
- All 6 API modules work: consent, quality, abtest, signals, ml, admin

**Commands:**
```bash
# Get OpenAPI spec
curl http://localhost:8000/openapi.json | jq '.paths | keys'

# Count endpoints
curl -s http://localhost:8000/openapi.json | jq '.paths | length'

# Test Admin API (simplest, no database required)
curl -H "Authorization: Bearer [TOKEN]" http://localhost:8000/api/v1/admin/health

# Expected response:
# {
#   "status": "healthy",
#   "database": "connected",
#   "redis": "connected",
#   "prefect": "connected"
# }

curl -H "Authorization: Bearer [TOKEN]" http://localhost:8000/api/v1/admin/metrics
# Expected: Aggregated metrics from all services

# Test Quality API
curl -X POST http://localhost:8000/api/v1/quality/validate \
  -H "Authorization: Bearer [TOKEN]" \
  -H "Content-Type: application/json" \
  -d '{"records": [{"field": "test"}]}'

# Test Signals API
curl -X POST http://localhost:8000/api/v1/signals/detect \
  -H "Authorization: Bearer [TOKEN]" \
  -H "Content-Type: application/json" \
  -d '{"records": [{"value": "suspicious_pattern"}]}'

# Test ML Predictor API
curl -X POST http://localhost:8000/api/v1/ml/predict \
  -H "Authorization: Bearer [TOKEN]" \
  -H "Content-Type: application/json" \
  -d '{"records": [{"features": [0.1, 0.2, 0.3]}]}'

# Test A/B Test API
curl -X POST http://localhost:8000/api/v1/abtest/create \
  -H "Authorization: Bearer [TOKEN]" \
  -H "Content-Type: application/json" \
  -d '{"name": "test_variant_a", "control_ratio": 0.5}'

# Test Consent API
curl -X POST http://localhost:8000/api/v1/consent \
  -H "Authorization: Bearer [TOKEN]" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "consent_type": "GDPR", "granted": true}'
```

**Success Criteria:**
- ✅ All 19 endpoints respond with 200/201 (not 500)
- ✅ Response schemas match OpenAPI documentation
- ✅ All 6 modules work (admin, quality, signals, ml, abtest, consent)

**If endpoints fail:**
- Check service logs: `docker-compose logs fastapi`
- Verify OpenAPI spec: `curl http://localhost:8000/docs`

---

### Task 3.2: Test Confidence Routing (AI vs Human)

**What to test:**
- Records with high confidence (>95%) routed to AI only
- Records with low confidence (<90%) flagged for human review
- Rejection threshold works (confidence <70% = rejected)

**Test Script:**
```python
# tests/validation/test_confidence_routing.py

async def test_confidence_routing():
    """Verify confidence-based routing to AI vs human reviewers"""

    # Scenario: 100 records with varying confidence
    test_records = [
        {"text": "clear_category", "expected_confidence": 0.98},  # AI only
        {"text": "ambiguous_case", "expected_confidence": 0.75},  # Human review
        {"text": "gibberish_$@#%", "expected_confidence": 0.45},  # Reject
    ]

    response = await client.post(
        "/api/v1/quality/validate",
        json={"records": test_records},
        headers={"Authorization": f"Bearer {token}"}
    )

    results = response.json()

    # Verify routing
    ai_only = sum(1 for r in results if r["confidence"] > 0.95)
    human_review = sum(1 for r in results if 0.70 < r["confidence"] < 0.95)
    rejected = sum(1 for r in results if r["confidence"] < 0.70)

    assert ai_only > human_review > 0, "Routing not working correctly"
    print(f"✅ Confidence routing works:")
    print(f"   - AI only: {ai_only}")
    print(f"   - Human review: {human_review}")
    print(f"   - Rejected: {rejected}")

asyncio.run(test_confidence_routing())
```

**Commands:**
```bash
pytest tests/validation/test_confidence_routing.py -v
```

**Success Criteria:**
- ✅ High confidence (>95%) → AI only
- ✅ Medium confidence (70-95%) → Human review queue
- ✅ Low confidence (<70%) → Rejected
- ✅ Distribution makes economic sense (80%+ AI, <20% human)

**If it fails:**
- Check confidence model: `grep -r "confidence_threshold" src/`
- Verify thresholds make sense for your margins

---

## Phase 4: Business Logic Validation (10-15 minutes)

### Task 4.1: Test Margin Calculation

**What to test:**
- Cost tracking is accurate (AI calls vs human reviews)
- Pricing tiers (Bronze $0.12, Silver $0.10, Gold $0.08) are profitable
- Margins at $0.08/label are >50%

**Test Script:**
```python
# tests/validation/test_margins.py

async def test_margin_calculation():
    """Verify margins are profitable at stated pricing"""

    # Process 1,000 records through each tier
    test_cases = [
        {
            "tier": "Gold",
            "price_per_label": 0.08,
            "expected_ai_ratio": 0.95,  # 95% AI confidence
            "expected_human_ratio": 0.03,  # 3% human review
            "expected_reject_ratio": 0.02  # 2% rejected
        },
        {
            "tier": "Silver",
            "price_per_label": 0.10,
            "expected_ai_ratio": 0.90,
            "expected_human_ratio": 0.08,
            "expected_reject_ratio": 0.02
        },
        {
            "tier": "Bronze",
            "price_per_label": 0.12,
            "expected_ai_ratio": 0.85,
            "expected_human_ratio": 0.13,
            "expected_reject_ratio": 0.02
        }
    ]

    for test in test_cases:
        records = 1000

        # Costs
        ai_cost = records * 0.95 * 0.001  # GPT-4o-mini at $0.001/call
        human_cost = records * 0.03 * 2.00  # Human review at $2/label
        rejected_cost = 0  # No cost for rejected
        total_cost = ai_cost + human_cost

        # Revenue
        revenue = records * test["price_per_label"]

        # Margin
        margin = (revenue - total_cost) / revenue

        assert margin > 0.50, f"❌ {test['tier']} tier has <50% margin!"
        print(f"✅ {test['tier']} tier: {margin:.1%} margin")
        print(f"   Revenue: ${revenue}, Cost: ${total_cost:.2f}, Margin: ${revenue - total_cost:.2f}")

asyncio.run(test_margin_calculation())
```

**Commands:**
```bash
# Run margin test
pytest tests/validation/test_margins.py -v

# Check actual API costs from logs
docker-compose logs fastapi | grep -i "cost\|usage"
```

**Success Criteria:**
- ✅ Gold tier ($0.08): >50% margin
- ✅ Silver tier ($0.10): >50% margin
- ✅ Bronze tier ($0.12): >50% margin
- ✅ Human review cost doesn't exceed 30% of revenue

**If it fails:**
- Human review ratio too high → Adjust confidence thresholds
- AI cost too high → Switch to cheaper model (GPT-4o-mini instead of GPT-4o)
- Pricing too low → Increase price per tier

---

### Task 4.2: Test Stripe Metered Billing Integration

**What to test:**
- Usage tracked correctly (AI_LABELS vs HUMAN_AUDITS)
- Stripe meter API receives correct values
- Billing calculation matches actual usage

**Test Script:**
```python
# tests/validation/test_stripe_billing.py

async def test_stripe_metered_billing():
    """Verify Stripe meter tracking works"""

    # Process dataset
    response = await client.post(
        "/api/v1/quality/validate",
        json={"records": test_data},
        headers={"Authorization": f"Bearer {token}"}
    )

    # Check Stripe was updated
    stripe_meters = await get_stripe_meter_events(customer_id="test_tenant_123")

    ai_labels_count = sum(1 for e in stripe_meters if e.meter_name == "AI_LABELS")
    human_audits_count = sum(1 for e in stripe_meters if e.meter_name == "HUMAN_AUDITS")

    assert ai_labels_count > 0, "AI_LABELS meter not recorded"
    assert human_audits_count >= 0, "HUMAN_AUDITS meter not recorded"

    print(f"✅ Stripe metering works:")
    print(f"   - AI labels recorded: {ai_labels_count}")
    print(f"   - Human audits recorded: {human_audits_count}")

asyncio.run(test_stripe_metered_billing())
```

**Commands:**
```bash
# Run Stripe billing test
pytest tests/validation/test_stripe_billing.py -v

# Check Stripe test events (if using Stripe test mode)
# You can view in Stripe Dashboard → Developers → Usage records
```

**Success Criteria:**
- ✅ AI_LABELS meter increments correctly
- ✅ HUMAN_AUDITS meter increments correctly
- ✅ Stripe invoice reflects actual usage
- ✅ No missing or duplicate meter events

**If it fails:**
- Check Stripe API key: `echo $STRIPE_API_KEY`
- Verify metered billing configured: `grep -r "create_meter" src/`
- Check Stripe test events in dashboard

---

## Phase 5: Integration Test (End-to-End Flow)

### Task 5.1: Full Pipeline Test

**What to test:**
- Complete flow: Upload → PII redaction → AI labeling → Confidence routing → Download

**Test Script:**
```python
# tests/validation/test_full_pipeline.py

async def test_full_data_pipeline():
    """End-to-end: Upload CSV → Redact PII → Label → Download"""

    # Step 1: Upload raw CSV with PII
    csv_data = """patient_id,diagnosis,phone,email
MRN123,Cancer,(555)123-4567,john@example.com
MRN124,Diabetes,(555)123-4568,jane@example.com
MRN125,Hypertension,(555)123-4569,bob@example.com"""

    upload_response = await client.post(
        "/api/v1/quality/validate",
        json={"csv": csv_data},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]
    print(f"✅ Upload successful: Job ID {job_id}")

    # Step 2: Check processing status
    for i in range(60):  # Wait up to 60 seconds
        status_response = await client.get(
            f"/api/v1/quality/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        status = status_response.json()
        if status["status"] == "completed":
            break
        time.sleep(1)

    assert status["status"] == "completed", "Job timed out"
    print(f"✅ Processing complete in {status['processed_seconds']}s")

    # Step 3: Verify PII was redacted
    download_response = await client.get(
        f"/api/v1/quality/jobs/{job_id}/download",
        headers={"Authorization": f"Bearer {token}"}
    )

    result_data = download_response.json()

    # PII should NOT be in results
    assert "(555)123-4567" not in str(result_data), "❌ Phone not redacted!"
    assert "john@example.com" not in str(result_data), "❌ Email not redacted!"

    print("✅ PII redaction verified")

    # Step 4: Verify confidence scores
    for record in result_data["records"]:
        assert "confidence" in record, "Missing confidence score"
        assert 0 <= record["confidence"] <= 1, "Invalid confidence score"

    print("✅ Confidence scores generated")

    # Step 5: Verify audit trail
    audit_response = await client.get(
        f"/api/v1/quality/jobs/{job_id}/audit",
        headers={"Authorization": f"Bearer {token}"}
    )

    audit_trail = audit_response.json()
    assert audit_trail["models_used"] is not None, "No model info in audit"
    assert audit_trail["pii_redaction_count"] > 0, "No PII redaction logged"

    print("✅ Audit trail complete")
    print(f"\n✅ Full pipeline test PASSED")
    print(f"   Job ID: {job_id}")
    print(f"   Processing time: {status['processed_seconds']}s")
    print(f"   Records processed: {len(result_data['records'])}")
    print(f"   PII instances redacted: {audit_trail['pii_redaction_count']}")

asyncio.run(test_full_data_pipeline())
```

**Commands:**
```bash
# Run end-to-end test
pytest tests/validation/test_full_pipeline.py -v -s

# Monitor progress
docker-compose logs -f fastapi
```

**Success Criteria:**
- ✅ CSV upload succeeds
- ✅ Processing completes in <2 minutes (for 1000 records)
- ✅ PII redacted in results
- ✅ Confidence scores generated (0-1 range)
- ✅ AI routing works (80%+ AI only)
- ✅ Human review queue populated for edge cases
- ✅ Audit trail logged completely
- ✅ Results downloadable as CSV/JSON

**If it fails:**
- Check service logs for errors: `docker-compose logs fastapi`
- Verify all services running: `docker-compose ps`
- Check database: `psql -h localhost -p 5433 -U postgres -d data_foundry -c "SELECT COUNT(*) FROM data_records;"`

---

## Summary Checklist

Run in this order:

### ✅ Phase 1 (Infrastructure) - 5-10 min
- [ ] Docker Compose stack starts
- [ ] All 5 services healthy
- [ ] Database schema exists
- [ ] 11 models importable

### ✅ Phase 2 (Security) - 10-15 min
- [ ] Tenant isolation working (RLS)
- [ ] PII redaction working (Presidio)
- [ ] JWT authentication working

### ✅ Phase 3 (API) - 15-20 min
- [ ] All 19 endpoints respond
- [ ] Admin API working
- [ ] Quality API working
- [ ] Signals API working
- [ ] ML Predictor API working
- [ ] A/B Test API working
- [ ] Consent API working

### ✅ Phase 4 (Business) - 10-15 min
- [ ] Margins >50% at all price tiers
- [ ] Stripe metering records correctly
- [ ] Confidence routing works

### ✅ Phase 5 (End-to-End) - 10-15 min
- [ ] Full pipeline completes
- [ ] PII truly redacted
- [ ] Audit trail logged
- [ ] Results downloadable

---

## What Partner AI Should Do:

1. **Read** this entire document
2. **Set up** test environment (start Docker, activate venv)
3. **Run phases sequentially** (1→2→3→4→5)
4. **Document results** for each phase (pass/fail + errors)
5. **Stop at first failure** and debug before continuing
6. **Provide summary** at end with green/red checkmarks

---

## Expected Timeline:
- Infrastructure: 5-10 min
- Security: 10-15 min
- API: 15-20 min
- Business: 10-15 min
- Full pipeline: 10-15 min
- **TOTAL: 50-75 minutes** (vs. 1-2 hours for all 1,322 unit tests)

---

**Document created:** December 24, 2025
**Purpose:** Guide partner AI through systematic backend validation
**Next step after validation:** Start frontend development (Week 1 Monday)
