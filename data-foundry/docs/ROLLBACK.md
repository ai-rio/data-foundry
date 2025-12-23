# Rollback Procedures - v4-df-migration

**Purpose:** Document rollback procedures for each week of the migration.

## General Rollback Principles

1. **Feature Flags First:** All new features are behind feature flags
2. **Git Revert Second:** Code changes can be reverted via git
3. **Database Last:** Schema changes require careful handling
4. **Data Preservation:** Never delete data during rollback

---

## Week 1 Rollback: Data Validation + Database Optimization

### Rollback Trigger Conditions
- Processing time increase >15%
- Test failures >20% of test suite
- Data quality validator false positive rate >10%
- Database performance degradation (not improvement)

### Rollback Steps

**Step 1: Disable Feature Flags** (Immediate, <1 minute)
```bash
# Set in .env or config
ENABLE_DATA_VALIDATION=false
ENABLE_STAGING_LAYER=false
MIN_QUALITY_SCORE=0.0  # Accept all records

# Restart services
systemctl restart data-foundry  # or equivalent
```

**Step 2: Verify System Recovery** (<5 minutes)
```bash
# Check processing pipeline
pytest tests/test_ingestion_flow.py -v

# Verify no records are being filtered
grep "quality_score" logs/ingestion.log | tail -20
```

**Step 3: Code Rollback (if needed)** (<10 minutes)
```bash
# Identify Week 1 commits
git log --oneline --grep="Week 1\|data quality\|staging\|validation" -10

# Revert Week 1 changes
git revert <commit-range>

# Example: git revert abc123..def456

# Push revert
git push origin feature/v4-df-migration
```

**Step 4: Database Rollback** (if schema changes)
```bash
# Check for migrations
ls -la migrations/ | grep week1

# Rollback migration
alembic downgrade -1

# Or manual SQL if needed
psql -f migrations/rollback_week1.sql
```

### Rollback Verification
```bash
# Run full test suite
pytest tests/ -v --cov

# Check system metrics
curl http://localhost:8000/health
```

---

## Week 2 Rollback: A/B Testing Framework

### Rollback Trigger Conditions
- A/B assignment failure rate >5%
- Metrics collection not working
- Treatment distribution skewed (>60/40 instead of 50/50)

### Rollback Steps

**Step 1: Disable A/B Testing** (Immediate)
```bash
# Set in config
ENABLE_AB_TESTING=false
AB_TEST_RATIO=0.0  # No traffic to treatment

# Restart services
```

**Step 2: Verify Pipeline Works** (<5 minutes)
```bash
# All records should go to control/baseline
pytest tests/test_ingestion_flow.py -v

# Check A/B logs
grep "AB_TESTING_DISABLED" logs/ab_testing.log
```

**Step 3: Code Rollback** (if needed)
```bash
git log --oneline --grep="Week 2\|A/B testing\|ab_testing" -10
git revert <commit-range>
```

### Rollback Verification
```bash
# Verify no A/B artifacts
pytest tests/unit/test_ab_testing.py -v -k "test_disabled"
```

---

## Week 3 Rollback: Signal Detection

### Rollback Trigger Conditions
- Signal detection precision <70%
- Signal detection recall <60%
- Too many records filtered (>90% filtered)
- Processing time increase >20%

### Rollback Steps

**Step 1: Disable Signal Detection** (Immediate)
```bash
ENABLE_SIGNAL_DETECTION=false
SIGNAL_DETECTION_THRESHOLD=100.0  # Accept all records

# Restart services
```

**Step 2: Verify AI Processing Normal** (<5 minutes)
```bash
# All records should reach AI labeling
pytest tests/test_ai_labeling.py -v

# Check signal detection is bypassed
grep "SIGNAL_DETECTION_DISABLED" logs/signal_detector.log
```

**Step 3: Code Rollback** (if needed)
```bash
git log --oneline --grep="Week 3\|signal detection\|signal_detector" -10
git revert <commit-range>
```

### Rollback Verification
```bash
# Verify cost reduction claims are accurate
pytest tests/test_signal_detector.py -v -k "test_cost_validation"
```

---

## Complete Rollback (All Weeks)

### Emergency Rollback - All Features

**Step 1: Disable All Feature Flags**
```bash
# .env configuration
ENABLE_DATA_VALIDATION=false
ENABLE_STAGING_LAYER=false
ENABLE_AB_TESTING=false
ENABLE_SIGNAL_DETECTION=false
MIN_QUALITY_SCORE=0.0
SIGNAL_DETECTION_THRESHOLD=100.0
```

**Step 2: Revert to Pre-Migration State**
```bash
# Identify migration start commit
git log --oneline --grep="v4-df-migration" -1
PRE_MIGRATION_COMMIT=<commit-hash>

# Reset branch (CAUTION: this discards all changes)
git reset --hard $PRE_MIGRATION_COMMIT
git push --force origin feature/v4-df-migration
```

**Step 3: Verify Baseline Behavior**
```bash
# Run baseline tests
pytest tests/test_ingestion_flow.py -v

# Check system health
curl http://localhost:8000/health
```

---

## Rollback Decision Tree

```
Is processing time degraded?
├── Yes (>15%) → Disable feature flags → Wait 5 min → Still degraded?
│   ├── Yes → Revert code changes
│   └── No → Monitor
└── No → Continue

Are tests failing?
├── Yes (>20%) → Check test integrity → Test issue?
│   ├── Yes → Fix test
│   └── No → Disable feature → Investigate
└── No → Continue

Is AI cost not reduced?
├── Yes (no reduction) → Check quality scores → Too aggressive?
│   ├── Yes → Adjust MIN_QUALITY_SCORE
│   └── No → Check signal detection
└── No → Success!
```

---

## Rollback Escalation Path

| Severity | Action | Timeline | Owner |
|----------|--------|----------|-------|
| Minor (<5% impact) | Adjust feature flags | Immediate | Developer |
| Moderate (5-20% impact) | Disable weekly feature | <5 min | Tech Lead |
| Major (>20% impact) | Revert week changes | <15 min | Tech Lead |
| Critical (system down) | Complete rollback | <30 min | Engineering Manager |

---

## Rollback Testing

Before each week's deployment:
1. **Practice rollback** in staging environment
2. **Document rollback time** for each step
3. **Update this document** with any lessons learned

---

## Contact Information

**Tech Lead:** [Contact]
**On-Call Engineer:** [Contact]
**Emergency Channel:** [Slack/Phone]

---

**Created:** 2025-12-23
**Purpose:** v4-df-migration Preflight Check - QA Audit Critical Issue #4
**Next Review:** After each rollback drill
