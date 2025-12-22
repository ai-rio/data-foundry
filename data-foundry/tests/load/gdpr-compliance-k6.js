/**
 * Phase 6.5 GDPR Compliance Load Test
 *
 * Tests GDPR endpoints under load:
 * - Consent Recording (Article 7)
 * - Consent Verification
 * - Data Subject Rights (Articles 17, 20, 21)
 * - Audit Trail Access
 *
 * SLA: P99 latency <1500ms, error rate <0.1%, 99.9% compliance logging
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_TOKEN = __ENV.API_TOKEN || 'test-token';

export const options = {
  stages: [
    { duration: '1m', target: 50 },    // Warm-up
    { duration: '3m', target: 200 },   // Ramp up
    { duration: '5m', target: 500 },   // Peak load (GDPR requirements)
    { duration: '3m', target: 500 },   // Sustained peak
    { duration: '2m', target: 100 },   // Cool down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<1200', 'p(99)<1500'],
    'http_req_failed': ['rate<0.001'],  // <0.1% for GDPR critical endpoints
    'http_req_waiting': ['p(99)<1000'],
    'consent_recording_success_rate': ['rate>0.999'],
    'audit_trail_completeness': ['rate>0.999'],
  },
};

// Test data generators
function generateConsentData() {
  return {
    user_id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    consent_text: "I consent to the processing of my personal data for analytics purposes as described in the privacy policy. This is specific, informed, and unambiguous consent meeting GDPR Article 7 requirements.",
    data_categories: ["analytics", "marketing", "personalization"],
    lawful_basis: "consent",
    purposes: ["data_analysis", "personalized_content", "marketing_communications"],
    retention_period_days: 1825, // 5 years
    tenant_id: "test-tenant-gdpr-load",
  };
}

function generateDataSubjectRequest() {
  return {
    user_id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    request_type: "data_portability", // Could be "erasure", "access", "portability", "objection"
    justification: "Exercising GDPR Article 20 right to data portability",
    tenant_id: "test-tenant-gdpr-load",
  };
}

export default function () {
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + API_TOKEN,
      'X-Request-ID': `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    },
  };

  // Test 1: Consent Recording (Article 7)
  group('GDPR - Consent Recording (Article 7)', () => {
    const consentData = JSON.stringify(generateConsentData());

    let res = http.post(`${BASE_URL}/api/v1/consent/record`, consentData, params);

    const consentSuccess = check(res, {
      'consent recording status is 201': (r) => r.status === 201,
      'consent recording response time < 1s': (r) => r.timings.duration < 1000,
      'consent recording has response body': (r) => r.body.length > 0,
      'consent ID returned': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.consent_id && body.consent_id.length > 0;
        } catch (e) {
          return false;
        }
      },
      'compliant consent text': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.consent_text && body.consent_text.length >= 50;
        } catch (e) {
          return false;
        }
      },
    });

    // Custom metric for compliance
    if (!consentSuccess) {
      console.error(`Consent Recording Failed: ${res.status} - ${res.body}`);
    }

    sleep(1);
  });

  // Test 2: Consent Verification
  group('GDPR - Consent Verification', () => {
    const userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    let res = http.get(`${BASE_URL}/api/v1/consent/verify?user_id=${userId}`, params);

    check(res, {
      'consent verification status is 200': (r) => r.status === 200,
      'consent verification response time < 500ms': (r) => r.timings.duration < 500,
      'consent verification has audit trail': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.audit_trail && Array.isArray(body.audit_trail);
        } catch (e) {
          return false;
        }
      },
    });

    sleep(0.5);
  });

  // Test 3: Data Subject Rights (Articles 17, 20, 21)
  group('GDPR - Data Subject Rights', () => {
    const requestData = JSON.stringify(generateDataSubjectRequest());

    // Test Right to Erasure (Article 17)
    let erasureRequest = {
      ...JSON.parse(requestData),
      request_type: "erasure",
      justification: "Exercising GDPR Article 17 right to erasure"
    };

    let res = http.post(`${BASE_URL}/api/v1/data-subject/erasure`, JSON.stringify(erasureRequest), params);

    check(res, {
      'erasure request status is 202': (r) => r.status === 202,
      'erasure request acknowledged': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.acknowledged === true && body.estimated_completion_hours <= 30;
        } catch (e) {
          return false;
        }
      },
    });

    sleep(1);
  });

  // Test 4: Audit Trail Access (GDPR Compliance Requirement)
  group('GDPR - Audit Trail Access', () => {
    const userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    let res = http.get(`${BASE_URL}/api/v1/audit/trail?user_id=${userId}&limit=10`, params);

    check(res, {
      'audit trail status is 200': (r) => r.status === 200,
      'audit trail response time < 800ms': (r) => r.timings.duration < 800,
      'audit trail has immutable records': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.audit_records && Array.isArray(body.audit_records) &&
                 body.audit_records.every(record => record.immutable === true);
        } catch (e) {
          return false;
        }
      },
      'audit trail includes timestamps': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.audit_records &&
                 body.audit_records.every(record => record.timestamp && record.action);
        } catch (e) {
          return false;
        }
      },
    });

    sleep(0.8);
  });

  // Test 5: Consent Withdrawal (Article 7.3)
  group('GDPR - Consent Withdrawal', () => {
    const consentData = generateConsentData();
    const withdrawalData = {
      consent_id: consentData.user_id, // In real scenario, this would be actual consent ID
      withdrawal_reason: "No longer consent to processing for marketing purposes",
      legal_basis_change: false,
      immediate_effect: true,
    };

    let res = http.post(`${BASE_URL}/api/v1/consent/withdraw`, JSON.stringify(withdrawalData), params);

    check(res, {
      'withdrawal status is 200': (r) => r.status === 200,
      'withdrawal processed immediately': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.withdrawn_at && body.status === "withdrawn";
        } catch (e) {
          return false;
        }
      },
      'audit trail updated': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.audit_trail_updated === true;
        } catch (e) {
          return false;
        }
      },
    });

    sleep(0.7);
  });

  // Small think time between user sessions
  sleep(2);
}