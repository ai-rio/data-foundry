# Load Testing Quick Reference Guide
## Phase 6.5 Validation - Team Documentation

---

## Running Load Tests

### Option 1: Host Networking (Recommended)
```bash
cd /home/carlos/projects/data_foundry/data-foundry
./scripts/k6-run-test.sh
```

### Option 2: Custom Network
```bash
./scripts/k6-network-test.sh
```

### Option 3: Docker Compose
```bash
docker-compose -f docker-compose.loadtest.yml --profile loadtest up k6
```

---

## Troubleshooting Common Issues

### k6 Cannot Connect to API
**Error**: `connection refused`
```bash
# Verify API is running
curl http://localhost:8000/health

# Use host networking
docker run --network host grafana/k6:latest
```

### Volume Mount Issues
**Error**: `no such file or directory`
```bash
# Use stdin redirection instead
k6 run - < script.js
```

### Missing API Token
**Error**: `Authorization header missing`
```bash
# Get fresh token
curl -s http://localhost:8000/test-token
```

---

## Key File Locations

```
/data-foundry/
├── docs/
│   ├── PHASE_6_5_VALIDATION_ROADMAP.md     # Main validation plan
│   ├── WEEK_1_VALIDATION_RESULTS.md        # Detailed results
│   └── WEEK_1_EXECUTIVE_SUMMARY.md         # Stakeholder summary
├── scripts/
│   ├── k6-run-test.sh                      # Primary load test script
│   ├── k6-network-test.sh                  # Custom network version
│   └── k6-host-ip-test.sh                  # Fallback solution
├── tests/load/
│   └── k6-ramp-up.js                       # Load test configuration
├── results/
│   ├── ramp-up.json                        # Test results (930MB)
│   └── zap.yaml                            # Security scan results
└── docker-compose.loadtest.yml             # Docker setup
```

---

## Test Configuration

### Current Load Profile
- **Duration**: 19 minutes total
- **Max VUs**: 500 concurrent users
- **Target**: 500 RPS sustained
- **Test Data**: Synthetic JSON payloads

### Thresholds
```javascript
{
  'http_req_duration': ['p(95)<1800', 'p(99)<2200'],
  'http_req_failed': ['rate<0.0005'],
  'http_req_waiting': ['p(99)<1500']
}
```

---

## Analyzing Results

### Quick Summary
```bash
# Total requests
grep '"metric":"http_reqs"' results/ramp-up.json | wc -l

# Error count
grep '"status":"500"' results/ramp-up.json | wc -l

# Average response time (approximate)
grep '"metric":"http_req_duration"' results/ramp-up.json | jq '.data.value' | awk '{sum+=$1; count++} END {print sum/count}'
```

### Using k6 Tools
```bash
# Install k6 locally for analysis
brew install k6  # Mac
apt-get install k6  # Linux

# Process results
k6 parse results/ramp-up.json --output-format=csv > results.csv
```

---

## Security Testing

### Run OWASP ZAP Scan
```bash
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t http://localhost:8000 \
  -r results/security-report.html
```

### Check Results
```bash
# Count issues by level
grep -E "High|Medium|Low" results/zap.yaml
```

---

## Performance Monitoring

### System Resources During Test
```bash
# CPU and Memory
htop

# Network connections
netstat -an | grep :8000

# Docker stats
docker stats
```

### Application Logs
```bash
# API container logs
docker logs data_foundry_api -f

# Database connections
docker exec -it data_foundry_db psql -U foundry_user -c "SELECT count(*) FROM pg_stat_activity;"
```

---

## Next Steps Checklist

- [ ] Deploy missing microservices for full API coverage
- [ ] Profile and fix p(99) latency (>4s)
- [ ] Set up APM monitoring (Week 2)
- [ ] Prepare for sustained load test (500 RPS × 4h)
- [ ] Document spike testing procedure

---

## Emergency Commands

### Stop All Tests
```bash
# Kill k6 containers
docker kill $(docker ps -q --filter "ancestor=grafana/k6")

# Reset network
docker network disconnect datafoundry-loadtest data_foundry_api 2>/dev/null || true
```

### Clean Results
```bash
# Archive current results
mv results/ramp-up.json results/ramp-up-$(date +%Y%m%d-%H%M%S).json

# Remove old results (>7 days)
find results/ -name "*.json" -mtime +7 -delete
```

---

## Contact Points

- **Performance Issues**: DevOps Team
- **Test Script Issues**: QA Team
- **Security Concerns**: Security Team
- **Infrastructure Problems**: Platform Team

---

*Last Updated: December 21, 2025*