#!/bin/bash

# Phase 6.5 K6 Load Testing Script
# Uses host networking to access localhost services

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$PROJECT_DIR/results"

# Ensure results directory exists
mkdir -p "$RESULTS_DIR"

# Get test token from API
echo "🔑 Getting test token from API..."
API_TOKEN=$(curl -s http://localhost:8000/test-token | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")

if [ -z "$API_TOKEN" ]; then
    echo "❌ Failed to get API token. Make sure API is running at http://localhost:8000"
    exit 1
fi

echo "✅ Token received (first 20 chars): ${API_TOKEN:0:20}..."

# Set environment variables
export BASE_URL="http://localhost:8000"
export API_TOKEN="$API_TOKEN"

# Run k6 with host networking using stdin redirection
echo "🚀 Starting k6 load test against localhost:8000..."
echo "📊 Results will be saved to: $RESULTS_DIR/ramp-up.json"

docker run --rm \
    --network host \
    -e BASE_URL="$BASE_URL" \
    -e API_TOKEN="$API_TOKEN" \
    -v "$RESULTS_DIR:/results" \
    -i grafana/k6:latest \
    run - < "$PROJECT_DIR/tests/load/k6-ramp-up.js" \
    --out json=/results/ramp-up.json

echo "✅ K6 load test completed!"
echo "📈 Results saved to: $RESULTS_DIR/ramp-up.json"

# Show summary
if [ -f "$RESULTS_DIR/ramp-up.json" ]; then
    echo ""
    echo "📊 Load Test Summary:"
    echo "- Results file: $RESULTS_DIR/ramp-up.json"
    echo "- File size: $(du -h "$RESULTS_DIR/ramp-up.json" | cut -f1)"
    echo "- Generated at: $(date)"
fi