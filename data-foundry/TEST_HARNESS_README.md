# Test Harness Documentation

Data Foundry has two test harnesses for different testing purposes:

## 1. Phase 1 Pipeline Test: `test_harness_pilot.py`

**Purpose:** Validate the backend ingestion pipeline (Phase 1 implementation)

**What it tests:**
- Direct function calls to the ingestion pipeline (no API)
- CSV data extraction, validation, quality scoring
- PII redaction and AI labeling
- Confidence routing (auto-approve vs human review)
- Cost calculation accuracy

**When to use:**
- Testing pipeline logic directly
- Validating Phase 0 assumptions (speed, accuracy, cost variance)
- Debugging pipeline issues
- Quick feedback without running API server

**Hardware friendly:**
- CSV only (no PDF/DOCX parsing)
- In-memory processing
- ~1000 records per vertical
- Runs in ~30-60 seconds total

**Example:**
```bash
cd data-foundry
source .venv/bin/activate
python test_harness_pilot.py
```

**Output:**
```
pilot_test_results/
├── fintech_result.json
├── healthcare_result.json
├── ecommerce_result.json
└── pilot_test_summary.csv
```

---

## 2. Phase 2 API Test: `test_harness_phase2_api.py`

**Purpose:** Validate file upload & job tracking API endpoints (Phase 2)

**What it tests:**
- POST /api/v1/upload - Multipart file upload
- GET /api/v1/jobs/{job_id} - Job status polling
- Cost validation (estimate vs actual)
- GET /api/v1/jobs/{job_id}/results - Results download

**When to use:**
- Testing API endpoints end-to-end
- Validating HTTP integration
- Measuring upload performance
- Testing job tracking and status polling
- Cost accuracy via API

**Hardware friendly:**
- CSV only (no PDF/DOCX parsing)
- Tests via HTTP (no direct function calls)
- ~1000 records per vertical
- Configurable polling intervals
- Graceful timeouts

**Prerequisites:**
- FastAPI server running on `http://localhost:8000`
- Environment variables:
  ```bash
  export API_BASE_URL="http://localhost:8000"
  export TENANT_ID="test-tenant-phase2"
  export API_KEY="test-key-phase2"
  ```

**Example:**
```bash
# Terminal 1: Start API server
cd data-foundry
source .venv/bin/activate
python -m uvicorn src.main:app --reload

# Terminal 2: Run API tests
cd data-foundry
source .venv/bin/activate
python test_harness_phase2_api.py
```

**Output:**
```
api_test_results/
├── fintech_api_result.json
├── healthcare_api_result.json
├── ecommerce_api_result.json
└── api_test_summary.csv
```

---

## Test Data Location

Both test harnesses use the same Kaggle datasets:
```
../data/pilot_test_datasets/
├── fintech/Banking_Transactions_USA_2023_2024.csv (5,389 records)
├── healthcare/healthcare_dataset.csv (55,500 records)
└── ecommerce/Phones.csv (170 records)
```

If not present, run:
```bash
python download_pilot_datasets.py
```

---

## Expected Results

### Phase 1 Pipeline Test

✅ **Success criteria:**
- All 3 verticals process successfully
- Processing time: <5s per vertical
- Cost variance: ≤5% from estimate
- No pipeline errors

Example output:
```
VERTICAL      | SUCCESS | TIME(s) | RECORDS | AUTO-APPR | HUMAN-REV | COST/REC
fintech       | ✓       |   0.40  |   1000  |     950   |     50    | $0.0045
healthcare    | ✓       |   2.10  |   1000  |     800   |    200    | $0.0285
ecommerce     | ✓       |   1.50  |    500  |     450   |     50    | $0.0095
```

### Phase 2 API Test

✅ **Success criteria:**
- All stages pass (Upload → Tracking → Cost → Download)
- Upload succeeds with valid job_id
- Job polling completes within timeout
- Cost variance ≤5%
- Results download contains correct record count

Example output:
```
VERTICAL  | SUCCESS | UPLOAD | TRACKING | COST_VAL | DOWNLOAD | TOTAL_TIME | COST_VAR%
fintech   | ✓       | ✓      | ✓        | ✓        | ✓        |      15.32 |     2.15
healthcare| ✓       | ✓      | ✓        | ✓        | ✓        |      45.20 |     1.89
ecommerce | ✓       | ✓      | ✓        | ✓        | ✓        |      18.75 |     0.50
```

---

## Troubleshooting

### Phase 1 Pipeline Test

**Issue:** ModuleNotFoundError for pipeline functions
```
from src.tasks.ingestion import extract_data
ModuleNotFoundError: No module named 'src.tasks.ingestion'
```
**Solution:** Ensure you're in the `data-foundry` directory and venv is activated

**Issue:** CSV not found
```
❌ Failed to load ..../data/pilot_test_datasets/fintech/...csv
```
**Solution:** Run `python download_pilot_datasets.py` to download test data

### Phase 2 API Test

**Issue:** Connection refused
```
httpx.ConnectError: Unable to connect to http://localhost:8000
```
**Solution:** Start the API server first: `python -m uvicorn src.main:app --reload`

**Issue:** 401 Unauthorized
```
Authorization failed: Bearer test-key-phase2
```
**Solution:** Check API_KEY and TENANT_ID environment variables

**Issue:** Job polling timeout
```
Timeout waiting for job completion (120s)
```
**Solution:** Check API server logs for job processing errors, or increase MAX_POLLS

---

## Configuration

### Phase 1 Pipeline Test

Edit constants in `test_harness_pilot.py`:
- `sample_size`: How many records to test per vertical (0 = all)
- Test selection: Modify the `tests` list in `main()`

### Phase 2 API Test

Environment variables:
```bash
export API_BASE_URL="http://localhost:8000"
export TENANT_ID="your-tenant-id"
export API_KEY="your-api-key"
```

Edit constants in `test_harness_phase2_api.py`:
- `API_TIMEOUT`: HTTP request timeout (default 120s)
- `POLL_INTERVAL`: Job status poll interval (default 1s)
- `MAX_POLLS`: Maximum polls before timeout (default 120)

---

## Extending the Tests

### Add a new vertical to Phase 1

1. Add dataset to `../data/pilot_test_datasets/{vertical}/`
2. Add test config to `tests` list:
```python
tests = [
    # ... existing tests ...
    PilotTestConfig(
        vertical="legal",
        dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/legal/contracts.csv"),
        sample_size=100,
    ),
]
```
3. Run: `python test_harness_pilot.py`

### Add a new vertical to Phase 2

Same as Phase 1, but for `test_harness_phase2_api.py`:
```python
tests = [
    # ... existing tests ...
    APITestConfig(
        vertical="legal",
        dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/legal/contracts.csv"),
        sample_size=100,
    ),
]
```

---

## CI/CD Integration

Both test harnesses are designed to be CI/CD friendly:

```bash
# Check if datasets exist
if [ ! -d "../data/pilot_test_datasets" ]; then
  python download_pilot_datasets.py
fi

# Run Phase 1 pipeline tests
python test_harness_pilot.py

# Check results
if grep -q '"success": true' pilot_test_results/fintech_result.json; then
  echo "✅ Phase 1 tests passed"
else
  echo "❌ Phase 1 tests failed"
  exit 1
fi

# Run Phase 2 API tests (requires server running)
python test_harness_phase2_api.py

# Check results
if grep -q '"success": true' api_test_results/fintech_api_result.json; then
  echo "✅ Phase 2 tests passed"
else
  echo "❌ Phase 2 tests failed"
  exit 1
fi
```

---

## Next Steps

### Phase 3: Comprehensive Validation

After both Phase 1 and Phase 2 tests pass:
1. Run 100 real datasets per vertical (not just 1000 records)
2. Measure accuracy, cost, and reliability at scale
3. Validate all Phase 0 assumptions hold

---

## Notes

- **No heavy parsing:** Both harnesses use CSV only to respect hardware constraints
- **Hardware efficient:** Async operations, minimal memory overhead
- **CI/CD ready:** Both return proper exit codes, generate structured output
- **Extensible:** Easy to add new verticals or modify test logic
