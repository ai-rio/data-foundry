# Baseline Measurement Script - v4-df-migration Preflight

**Purpose:** Establish performance and cost baselines before implementing Week 1 changes.

## Measurement Categories

### 1. Processing Time Baseline
**Metric:** Average time per record through ingestion pipeline

**Measurement Method:**
```bash
# Run existing ingestion test with timing
pytest tests/test_ingestion_flow.py -v --tb=short -k test_ingestion_pipeline --durations=10

# Extract timing data
grep -A 5 "call     tests/test_ingestion_flow.py" test_results.txt | awk '{print $4}'
```

**Target Baseline:** Record current average processing time (ms per record)

---

### 2. Database Query Performance Baseline
**Metric:** Query latency for hot paths

**Measurement Method:**
```bash
# Run database performance test
pytest tests/performance/test_database_performance.py -v --benchmark-only

# Key queries to measure:
# - DataRecord insertion
# - Tenant lookup
# - PII redaction queries
# - Human review queue updates
```

**Target Baseline:** Record average query latencies (ms)

---

### 3. AI Cost Baseline
**Metric:** Cost per AI operation

**Measurement Method:**
```python
# Run cost measurement script
python scripts/measure_ai_costs.py

# This will:
# 1. Process 100 sample records
# 2. Track API calls to LiteLLM
# 3. Calculate cost per operation
# 4. Generate baseline report
```

**Target Baseline:** Cost per 1000 records (USD)

---

### 4. Memory Usage Baseline
**Metric:** Memory consumption during peak load

**Measurement Method:**
```bash
# Run with memory profiling
python -m memory_profiler src/main.py &
MYPID=$!
ps aux | grep $MYPID | awk '{print $6}'
```

**Target Baseline:** Peak memory usage (MB)

---

## Baseline Recording Template

After running measurements, record results here:

```yaml
# Baseline Measurement Results - Date: YYYY-MM-DD
baseline_date: YYYY-MM-DD
git_commit: <commit-hash>
environment: <development/staging>

processing_time:
  avg_ms_per_record: <value>
  p50_ms: <value>
  p95_ms: <value>
  p99_ms: <value>

database_performance:
  datarecord_insert_ms: <value>
  tenant_lookup_ms: <value>
  pii_redaction_ms: <value>
  human_review_update_ms: <value>

ai_costs:
  cost_per_1k_records_usd: <value>
  api_calls_per_record: <value>
  avg_tokens_per_record: <value>

memory_usage:
  peak_mb: <value>
  avg_mb: <value>
  growth_rate_mb_per_hour: <value>
```

---

## Post-Week Measurement Validation

After each week, re-run measurements and validate:

### Week 1 Expected Changes:
- Processing time: <10% increase acceptable
- Database queries: 5-15% improvement expected
- AI costs: 30% reduction expected (via data quality filtering)
- Memory: Stable (no significant growth)

### Week 2 Expected Changes:
- Processing time: No significant change (A/B adds minimal overhead)
- A/B metrics collection functional

### Week 3 Expected Changes:
- AI costs: 60-95% total reduction (cumulative with Week 1)
- Signal detection >80% precision, >70% recall

---

## Quick Start Commands

```bash
# Run all baseline measurements
cd /home/carlos/projects/data_foundry/data-foundry

# 1. Processing time
pytest tests/test_ingestion_flow.py -v --durations=10 > results/baseline_processing_time.txt

# 2. Database performance
pytest tests/performance/test_database_performance.py -v --benchmark-only > results/baseline_db_perf.txt

# 3. AI costs (create this script first)
python scripts/measure_baseline_costs.py > results/baseline_ai_costs.yaml

# 4. Memory usage
python -m memory_profiler src/main.py > results/baseline_memory.txt
```

---

## Acceptance Criteria

Week 1 can proceed when:
- ✅ All 4 baseline measurements recorded
- ✅ Results documented in this file
- ✅ Baseline YAML file created in `results/baseline.yaml`

---

**Created:** 2025-12-23
**Purpose:** v4-df-migration Preflight Check - QA Audit Critical Issue #3
