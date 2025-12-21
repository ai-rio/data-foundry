#!/bin/bash

# Phase 6.5 K6 Load Testing with Custom Docker Network
# Creates dedicated network for load testing

set -e

# Configuration
NETWORK_NAME="datafoundry-loadtest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$PROJECT_DIR/results"

echo "🔧 Setting up Docker network for load testing..."

# Create custom network if it doesn't exist
if ! docker network inspect "$NETWORK_NAME" &>/dev/null; then
    echo "📡 Creating Docker network: $NETWORK_NAME"
    docker network create "$NETWORK_NAME"
else
    echo "✅ Docker network '$NETWORK_NAME' already exists"
fi

# Get API container name
API_CONTAINER=$(docker ps --filter "name=data_foundry_api" --format "{{.Names}}" | head -1)

if [ -z "$API_CONTAINER" ]; then
    echo "❌ API container not found. Make sure Docker stack is running."
    exit 1
fi

echo "🔗 Connecting API container '$API_CONTAINER' to load test network..."
docker network connect "$NETWORK_NAME" "$API_CONTAINER"

# Get test token
echo "🔑 Getting test token from API..."
API_TOKEN=$(curl -s http://localhost:8000/test-token | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")

if [ -z "$API_TOKEN" ]; then
    echo "❌ Failed to get API token."
    exit 1
fi

# Ensure results directory exists
mkdir -p "$RESULTS_DIR"

# Run k6 with custom network
echo "🚀 Starting k6 load test using Docker network..."
echo "📊 Results will be saved to: $RESULTS_DIR/ramp-up-network.json"

docker run --rm \
    --network "$NETWORK_NAME" \
    -e BASE_URL="http://data_foundry_api:8000" \
    -e API_TOKEN="$API_TOKEN" \
    -v "$PROJECT_DIR/tests:/tests" \
    -v "$RESULTS_DIR:/results" \
    grafana/k6:latest \
    run tests/load/k6-ramp-up.js \
    --out json=/results/ramp-up-network.json

echo "✅ K6 load test completed!"
echo "📈 Results saved to: $RESULTS_DIR/ramp-up-network.json"

# Cleanup (optional)
echo ""
echo "🧹 Cleanup options:"
echo "- Disconnect API: docker network disconnect $NETWORK_NAME $API_CONTAINER"
echo "- Remove network: docker network rm $NETWORK_NAME"