/**
 * Phase 6.5 Week 2 Load Test - Ramp-Up Pattern
 *
 * Tests: 50 → 500 RPS over 30 minutes
 * SLA: P99 latency <2000ms, error rate <5%
 * Week 2 Go/No-Go: No errors >5%, latency p99 <2s
 *
 * Run: k6 run tests/load/week2-ramp-up.js --out json=results/week2-ramp-up.json
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Dynamic token generation function
function getAuthToken() {
  const response = http.get(`${BASE_URL}/test-token`);
  if (response.status !== 200) {
    console.error('Failed to get auth token: ' + response.status);
    return 'fallback-test-token';
  }
  try {
    const data = JSON.parse(response.body);
    return data.access_token;
  } catch (e) {
    console.error('Failed to parse auth token response');
    return 'fallback-test-token';
  }
}

export const options = {
  stages: [
    { duration: '5m', target: 100 },    // 0-100 VUs (warm-up)
    { duration: '10m', target: 250 },   // 100-250 VUs (ramp)
    { duration: '10m', target: 500 },  // 250-500 VUs (ramp)
    { duration: '5m', target: 500 },    // stay at 500 (sustained)
    { duration: '3m', target: 0 },      // cool-down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<1800', 'p(99)<2000'],  // Week 2 targets
    'http_req_failed': ['rate<0.05'],  // <5% error rate (Week 2)
    'http_req_waiting': ['p(99)<1500'],
    'http_req_connecting': ['p(99)<100'],
  },
};

// Test data generator with more realistic payloads for Week 2
function generatePayload() {
  return {
    data: {
      id: 'week2_test_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
      text: 'Week 2 load testing data for sustained performance validation with larger content and more complex processing requirements',
      metadata: {
        timestamp: new Date().toISOString(),
        test_phase: 'week2',
        load_type: 'ramp-up'
      },
      content: {
        title: 'Performance Test Document',
        body: 'This is a larger test payload for Week 2 sustained load testing to validate system behavior under production-like conditions.',
        tags: ['performance', 'week2', 'load-test']
      }
    }
  };
}

export default function () {
  const payload = JSON.stringify(generatePayload());
  const apiToken = getAuthToken(); // Generate fresh token for each iteration
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + apiToken,
      'X-Test-Phase': 'week2',
      'X-Load-Type': 'ramp-up'
    },
    tags: { name: 'Week2-ProcessData' },
  };

  group('Week 2 Ramp-Up Test - Process Data Endpoint', () => {
    let res = http.post(BASE_URL + '/api/v1/process', payload, params);

    check(res, {
      'status is 200': (r) => r.status === 200,
      'response time < 2s': (r) => r.timings.duration < 2000,
      'response time < 2.2s': (r) => r.timings.duration < 2200, // Safety margin
      'has response body': (r) => r.body.length > 0,
      'response is JSON': (r) => {
        try {
          JSON.parse(r.body);
          return true;
        } catch (e) {
          return false;
        }
      },
      'processing successful': (r) => {
        try {
          const data = JSON.parse(r.body);
          return data.status === 'success' && data.output && data.output.enriched;
        } catch (e) {
          return false;
        }
      },
    });

    // Week 2 specific checks
    if (res.status !== 200) {
      console.error('Week 2 Error: ' + res.status + ' - ' + res.body);
    }

    // Small think time between requests (realistic user behavior)
    sleep(Math.random() * 0.5 + 0.5); // 0.5-1s random
  });
}