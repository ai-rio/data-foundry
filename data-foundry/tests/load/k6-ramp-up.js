/**
 * Phase 6.5 K6 Load Test - Ramp-Up Pattern
 *
 * Tests: 50 → 500 RPS over 20 minutes
 * SLA: P99 latency <2200ms, error rate <0.05%
 *
 * Run: k6 run tests/load/k6-ramp-up.js --out json=results/ramp-up.json
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';

// Configuration
const BASE_URL = __ENV.BASE_URL || 'https://api.datafoundry.com';
const API_TOKEN = __ENV.API_TOKEN || 'test-token';

export const options = {
  stages: [
    { duration: '2m', target: 100 },   // 50-100 VUs (warm-up)
    { duration: '5m', target: 250 },   // 100-250 VUs (ramp)
    { duration: '5m', target: 500 },   // 250-500 VUs (peak)
    { duration: '5m', target: 500 },   // stay at 500 (sustained)
    { duration: '2m', target: 0 },     // cool-down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<1800', 'p(99)<2200'],
    'http_req_failed': ['rate<0.0005'],  // <0.05%
    'http_req_waiting': ['p(99)<1500'],
  },
};

// Test data generator
function generatePayload() {
  return {
    data: {
      id: 'record_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
      text: 'Sample data for processing and enrichment with AI models',
      timestamp: new Date().toISOString(),
    }
  };
}

export default function () {
  const payload = JSON.stringify(generatePayload());
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + API_TOKEN,
    },
    tags: { name: 'ProcessData' },
  };

  group('Process Data Endpoint', () => {
    let res = http.post(BASE_URL + '/api/v1/process', payload, params);

    check(res, {
      'status is 200': (r) => r.status === 200,
      'response time < 2s': (r) => r.timings.duration < 2000,
      'response time < 2.2s': (r) => r.timings.duration < 2200,
      'response time < 500ms (p50)': (r) => r.timings.duration < 500,
      'has response body': (r) => r.body.length > 0,
      'response is JSON': (r) => {
        try {
          JSON.parse(r.body);
          return true;
        } catch (e) {
          return false;
        }
      },
    });

    // Custom metrics
    if (res.status !== 200) {
      console.error('Error: ' + res.status + ' - ' + res.body);
    }
  });

  // Small think time between requests
  sleep(1);
}
