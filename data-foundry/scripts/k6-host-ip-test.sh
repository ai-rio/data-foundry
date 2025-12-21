#!/bin/bash

# Phase 6.5 K6 Load Testing using Host IP
# Uses host machine IP for container communication

set -e

# Get host IP (works on Linux systems)
HOST_IP=$(ip route get 1.1.1.1 | awk '{print $7}' | head -1)

if [ -z "$HOST_IP" ]; then
    echo "❌ Could not determine host IP. Falling back to host.docker.internal"
    HOST_IP="host.docker.internal"
fi

echo "🌐 Using host IP: $HOST_IP"

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

# Set environment variables
export BASE_URL="http://$HOST_IP:8000"
export API_TOKEN="$API_TOKEN"

echo "🚀 Starting k6 load test against $BASE_URL..."
echo "📊 Results will be saved to: $RESULTS_DIR/ramp-up-host-ip.json"

# Run k6 with host IP
docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -e BASE_URL="$BASE_URL" \
    -e API_TOKEN="$API_TOKEN" \
    -v "$PROJECT_DIR/tests:/tests" \
    -v "$RESULTS_DIR:/results" \
    grafana/k6:latest \
    run tests/load/k6-ramp-up.js \
    --out json=/results/ramp-up-host-ip.json

echo "✅ K6 load test completed!"
echo "📈 Results saved to: $RESULTS_DIR/ramp-up-host-ip.json"