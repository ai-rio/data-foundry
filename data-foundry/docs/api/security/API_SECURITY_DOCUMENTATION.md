# API Documentation with Security Considerations
## Data Foundry Secure API Reference

**Version**: v1.0.0
**Date**: December 22, 2024
**Base URL**: https://api.datafoundry.com/v1
**Security Level**: Production Grade
**Authentication**: OAuth 2.0 + JWT + MFA

---

## API Security Overview

Data Foundry implements a comprehensive API security framework following OWASP API Security Top 10 and regulatory requirements. All APIs are secured with multiple layers of protection including authentication, authorization, input validation, rate limiting, and audit logging.

### Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   Rate Limiting │  │   Input         │  │   Output     │ │
│  │   (Per API Key) │  │   Validation    │  │   Filtering  │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Authentication Layer                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   OAuth 2.0     │  │   JWT           │  │   MFA        │ │
│  │   Authorization │  │   Verification  │  │   Verification│ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Authorization Layer                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   RBAC          │  │   ABAC          │  │   Scope      │ │
│  │   (Roles)       │  │   (Attributes)  │  │   Validation │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   Business      │  │   Data          │  │   Compliance │ │
│  │   Logic         │  │   Validation    │  │   Checks     │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Security Headers (All Endpoints)

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

---

## Authentication

### OAuth 2.0 Authorization Code Flow

```http
POST /oauth/authorize
Content-Type: application/x-www-form-urlencoded

response_type=code&
client_id={client_id}&
redirect_uri={redirect_uri}&
scope={scopes}&
state={state}
```

**Security Considerations:**
- PKCE (RFC 7636) is required for all public clients
- State parameter must be validated
- Redirect URIs must be pre-registered
- Authorization codes expire in 10 minutes

### Token Exchange

```http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic {base64(client_id:client_secret)}

grant_type=authorization_code&
code={authorization_code}&
redirect_uri={redirect_uri}&
code_verifier={code_verifier}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "def50200... (encrypted)",
  "scope": "consent:read consent:write",
  "id_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Refresh Token Flow

```http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic {base64(client_id:client_secret)}

grant_type=refresh_token&
refresh_token={refresh_token}
```

**Security Considerations:**
- Refresh tokens are encrypted and rotated
- Maximum of 5 active refresh tokens per client
- Refresh tokens expire after 30 days of inactivity

### JWT Verification

All API requests must include a valid JWT:

```http
Authorization: Bearer {jwt_token}
```

**JWT Structure:**
```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "2024-key-id"
  },
  "payload": {
    "iss": "https://auth.datafoundry.com",
    "sub": "user_123",
    "aud": "data-foundry-api",
    "exp": 1640995200,
    "iat": 1640991600,
    "auth_time": 1640991500,
    "nonce": "random-string",
    "acr": "urn:mace:incommon:iap:silver",
    "amr": ["pwd", "mfa"],
    "roles": ["data_processor"],
    "permissions": ["consent:read", "data:read"],
    "scope": "consent:read consent:write"
  }
}
```

---

## Consent Management APIs

### Record Consent

**Endpoint:** `POST /consent`
**Required Permissions:** `consent:write`

```http
POST /consent
Authorization: Bearer {jwt_token}
Content-Type: application/json
X-Request-ID: {unique_request_id}

{
  "user_id": "user_123",
  "consent_type": "data_processing",
  "consent_text": "I consent to Data Foundry processing my personal data for analytics purposes, including data analysis, trend identification, and service improvement. The data will be stored securely for 365 days and processed in accordance with applicable privacy laws.",
  "metadata": {
    "ip": "203.0.113.1",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "timestamp": "2024-01-01T10:00:00Z",
    "purpose": "analytics",
    "retention": "365_days",
    "data_categories": ["usage_data", "device_info"]
  }
}
```

**Response (201 Created):**
```json
{
  "consent_id": "consent_456",
  "user_id": "user_123",
  "consent_type": "data_processing",
  "status": "ACTIVE",
  "granted_at": "2024-01-01T10:00:00Z",
  "expires_at": "2025-01-01T10:00:00Z",
  "audit_id": "audit_789"
}
```

**Security Validation:**
- Input sanitization prevents injection attacks
- Rate limiting: 10 requests/minute per user
- Consent text minimum 100 characters
- IP address and user agent required
- All requests logged for audit trail

### Verify Consent

**Endpoint:** `GET /consent/{user_id}/{consent_type}/verify`
**Required Permissions:** `consent:read`

```http
GET /consent/user_123/data_processing/verify
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
```

**Response (200 OK):**
```json
{
  "has_consent": true,
  "consent_id": "consent_456",
  "granted_at": "2024-01-01T10:00:00Z",
  "status": "ACTIVE",
  "valid_until": "2025-01-01T10:00:00Z",
  "purposes": ["analytics", "service_improvement"],
  "last_verified": "2024-12-22T14:30:00Z"
}
```

### Withdraw Consent

**Endpoint:** `DELETE /consent/{user_id}/{consent_type}`
**Required Permissions:** `consent:write`

```http
DELETE /consent/user_123/data_processing
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
```

**Response (200 OK):**
```json
{
  "success": true,
  "consent_id": "consent_456",
  "withdrawn_at": "2024-12-22T14:30:00Z",
  "withdrawal_method": "api_request",
  "data_deletion_scheduled": true,
  "deletion_completion_estimate": "2024-12-22T16:30:00Z"
}
```

**Security Considerations:**
- Requires user or admin authorization
- Immediate processing stop on withdrawal
- Data deletion initiated within 2 hours
- Full audit trail of withdrawal

---

## Data Subject Rights APIs

### Access Request

**Endpoint:** `GET /data-subject/{user_id}/data`
**Required Permissions:** `data:read` or user authorization

```http
GET /data-subject/user_123/data?format=json
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
```

**Response (200 OK):**
```json
{
  "request_id": "dsr_789",
  "user_id": "user_123",
  "data_format": "json",
  "download_url": "https://secure-downloads.datafoundry.com/dsr_789?token=...",
  "expires_at": "2024-12-23T14:30:00Z",
  "data_summary": {
    "total_records": 156,
    "data_categories": ["personal_info", "usage_data", "consent_records"],
    "date_range": {
      "from": "2024-01-01",
      "to": "2024-12-22"
    }
  }
}
```

**Security Features:**
- Encrypted download links
- 24-hour expiration
- One-time use tokens
- Download tracking

### Erasure Request

**Endpoint:** `DELETE /data-subject/{user_id}/data`
**Required Permissions:** `data:delete` or user authorization

```http
DELETE /data-subject/user_123/data
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
Content-Type: application/json

{
  "retention_reasons": ["legal_requirement", "regulatory_compliance"],
  "exceptions": ["audit_logs", "fraud_detection"]
}
```

**Response (202 Accepted):**
```json
{
  "request_id": "erase_456",
  "status": "IN_PROGRESS",
  "estimated_completion": "2024-12-22T18:30:00Z",
  "records_to_delete": 156,
  "records_retained": 3,
  "retained_reasons": {
    "audit_logs": "7_years_required",
    "fraud_detection": "indefinite_retention"
  }
}

```

### Data Portability

**Endpoint:** `POST /data-subject/{user_id}/export`
**Required Permissions:** `data:read` or user authorization

```http
POST /data-subject/user_123/export
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
Content-Type: application/json

{
  "format": "csv",
  "include_consent_history": true,
  "include_processing_logs": false,
  "destination": {
    "type": "direct_transfer",
    "organization": "new_data_processor",
    "contact_email": "privacy@newprocessor.com"
  }
}
```

---

## Incident Management APIs

### Create Incident

**Endpoint:** `POST /incidents`
**Required Permissions:** `incident:create`

```http
POST /incidents
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
Content-Type: application/json

{
  "title": "Unauthorized database access detected",
  "description": "Multiple failed login attempts followed by successful access from unknown IP",
  "incident_type": "DATA_BREACH",
  "severity": "HIGH",
  "reported_by": "security@datafoundry.com",
  "affected_systems": ["database", "authentication"],
  "initial_impact": {
    "data_types": ["personal_data", "credentials"],
    "affected_users": "unknown",
    "duration": "15_minutes"
  },
  "metadata": {
    "source_ip": "198.51.100.1",
    "detection_method": "automated_monitoring",
    "confidence_score": 0.85
  }
}
```

**Response (201 Created):**
```json
{
  "incident_id": "inc_123",
  "status": "OPEN",
  "severity": "HIGH",
  "assigned_to": "incident_response_team",
  "created_at": "2024-12-22T10:00:00Z",
  "initial_actions": [
    "isolate_affected_systems",
    "preserve_evidence",
    "notify_stakeholders"
  ]
}
```

### Update Incident Status

**Endpoint:** `PUT /incidents/{incident_id}/status`
**Required Permissions:** `incident:update`

```http
PUT /incidents/inc_123/status
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
Content-Type: application/json

{
  "status": "CONTAINED",
  "reason": "Unauthorized access blocked, systems isolated",
  "updates": {
    "affected_users_identified": 150,
    "data_exfiltrated": false,
    "vulnerability_identified": "CVE-2024-1234"
  }
}
```

### Initiate GDPR Breach Notification

**Endpoint:** `POST /incidents/{incident_id}/gdpr-notification`
**Required Permissions:** `incident:notify`

```http
POST /incidents/inc_123/gdpr-notification
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
Content-Type: application/json

{
  "risk_assessment": {
    "likelihood": "high",
    "severity": "high",
    "affected_data": ["personal_data", "contact_information"],
    "consequences": ["identity_theft", "financial_loss"],
    "mitigation_measures": ["password_reset", "additional_monitoring"]
  },
  "affected_subjects_count": 150,
  "data_categories": ["name", "email", "address"],
  "contact_email": "dpo@datafoundry.com",
  "notification_preferences": {
    "notify_authority_immediately": true,
    "notify_subjects_immediately": true,
    "additional_recipients": ["legal@datafoundry.com"]
  }
}
```

---

## Security Monitoring APIs

### Security Events

**Endpoint:** `GET /security/events`
**Required Permissions:** `security:read`

```http
GET /security/events?from=2024-12-21T00:00:00Z&to=2024-12-22T23:59:59Z&severity=HIGH
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
```

**Response (200 OK):**
```json
{
  "events": [
    {
      "event_id": "evt_456",
      "timestamp": "2024-12-22T10:30:00Z",
      "event_type": "authentication_failure",
      "severity": "HIGH",
      "source_ip": "198.51.100.1",
      "user_id": "user_789",
      "details": {
        "failure_reason": "invalid_credentials",
        "attempts": 5,
        "locked": true
      },
      "mitigation": {
        "action_taken": "account_locked",
        "duration": "30_minutes"
      }
    }
  ],
  "total_events": 1,
  "page": 1,
  "per_page": 50
}
```

### Threat Intelligence

**Endpoint:** `GET /security/threats`
**Required Permissions:** `security:read`

```http
GET /security/threats?category=malware&severity=CRITICAL
Authorization: Bearer {jwt_token}
X-Request-ID: {unique_request_id}
```

---

## Rate Limiting and Quotas

### Rate Limits by Endpoint

| Endpoint | Rate Limit | Burst | Quota | Period |
|----------|------------|-------|-------|--------|
| POST /oauth/token | 10/min | 20 | 1000 | 1 hour |
| POST /consent | 100/min/user | 200 | 10000 | 1 hour |
| GET /consent/*/verify | 500/min/user | 1000 | 50000 | 1 hour |
| DELETE /consent/* | 10/min/user | 20 | 1000 | 1 hour |
| POST /incidents | 5/min | 10 | 100 | 1 hour |
| GET /security/events | 100/min | 200 | 10000 | 1 hour |

### Rate Limit Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640999999
X-RateLimit-Retry-After: 60
```

### Quota Management

```http
GET /api/quota
Authorization: Bearer {jwt_token}

Response:
{
  "current_usage": {
    "requests": 450,
    "data_processed": "2.5GB",
    "concurrent_sessions": 3
  },
  "limits": {
    "requests_per_hour": 1000,
    "data_per_month": "100GB",
    "max_concurrent_sessions": 5
  },
  "reset_times": {
    "requests": "2024-12-22T15:00:00Z",
    "data": "2025-01-01T00:00:00Z"
  }
}
```

---

## Input Validation and Sanitization

### Validation Rules

1. **String Fields**
   - Maximum length enforced per field
   - HTML/Script tags stripped
   - SQL injection patterns blocked
   - Unicode normalization applied

2. **Email Fields**
   - RFC 5322 compliance
   - MX record verification
   - Disposable email detection

3. **Date Fields**
   - ISO 8601 format required
   - Reasonable range validation
   - Future/past restrictions based on context

4. **JSON Payloads**
   - Schema validation
   - Size limits (1MB max)
   - Nested depth limits (10 levels max)

### Security Headers for Input

```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'
```

---

## Error Handling

### Standard Error Response Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input parameters",
    "details": [
      {
        "field": "email",
        "issue": "Invalid email format"
      },
      {
        "field": "consent_text",
        "issue": "Must be at least 100 characters"
      }
    ],
    "request_id": "req_123",
    "timestamp": "2024-12-22T10:30:00Z",
    "help_url": "https://docs.datafoundry.com/api/errors#validation_error"
  }
}
```

### Security-Specific Errors

| Error Code | HTTP Status | Description | Security Relevance |
|------------|-------------|-------------|-------------------|
| UNAUTHORIZED | 401 | Invalid or missing credentials | Authentication failure |
| FORBIDDEN | 403 | Insufficient permissions | Authorization failure |
| RATE_LIMITED | 429 | Too many requests | Rate limiting active |
| INVALID_TOKEN | 401 | JWT verification failed | Token security |
| MFA_REQUIRED | 428 | Multi-factor authentication required | Step-up authentication |
| SUSPICIOUS_ACTIVITY | 403 | Activity flagged as suspicious | Fraud detection |

---

## API Security Best Practices

### For API Consumers

1. **Secure Storage**
   - Store credentials securely (use vaults)
   - Never log access tokens
   - Rotate credentials regularly

2. **Network Security**
   - Always use HTTPS
   - Validate server certificates
   - Use certificate pinning in production

3. **Input Handling**
   - Validate all inputs client-side
   - Sanitize data before sending
   - Use parameterized queries

4. **Error Handling**
   - Never expose error details to users
   - Log errors securely
   - Implement graceful degradation

### For API Developers

1. **Authentication**
   - Implement token expiration
   - Use short-lived access tokens
   - Refresh token rotation

2. **Authorization**
   - Implement least privilege
   - Regular permission audits
   - Context-aware access control

3. **Data Protection**
   - Encrypt sensitive data
   - Implement data minimization
   - Audit data access

4. **Monitoring**
   - Log all security events
   - Implement real-time alerts
   - Regular security reviews

---

## Testing and Validation

### Security Testing Endpoints

```http
# Health check (no auth required)
GET /health

# Security headers test
GET /security/headers

# Authentication test
GET /auth/test
Authorization: Bearer {test_token}

# Permission test
GET /permissions/test
Authorization: Bearer {test_token}
```

### Test Credentials (Sandbox Only)

```json
{
  "test_user": {
    "username": "test_api_user",
    "password": "TestSecurePassword123!",
    "client_id": "test_client_id",
    "client_secret": "test_client_secret"
  }
}
```

### Postman Collection

A comprehensive Postman collection is available at:
https://docs.datafoundry.com/api/postman-collection

---

## SDKs and Libraries

### Official SDKs

| Language | Package | Version | Documentation |
|----------|---------|---------|---------------|
| Python | `datafoundry-sdk` | 1.0.0 | https://docs.datafoundry.com/sdk/python |
| JavaScript | `@datafoundry/api` | 1.0.0 | https://docs.datafoundry.com/sdk/js |
| Java | `com.datafoundry:api-sdk` | 1.0.0 | https://docs.datafoundry.com/sdk/java |
| .NET | `DataFoundry.SDK` | 1.0.0 | https://docs.datafoundry.com/sdk/dotnet |

### Quick Start Example (Python)

```python
from datafoundry_sdk import DataFoundryClient

# Initialize client
client = DataFoundryClient(
    client_id="your_client_id",
    client_secret="your_client_secret",
    base_url="https://api.datafoundry.com/v1"
)

# Record consent
consent = await client.consent.record(
    user_id="user_123",
    consent_type="data_processing",
    consent_text="Detailed consent text...",
    metadata={"ip": "192.168.1.1", "user_agent": "..."}
)

# Verify consent
has_consent = await client.consent.verify(
    user_id="user_123",
    consent_type="data_processing"
)
```

---

## Compliance and Certifications

### Compliance Standards

- **GDPR**: Full compliance (Articles 32, 33, 34)
- **HIPAA**: Security Rule compliance
- **SOC 2 Type II**: Security, Availability, Confidentiality
- **ISO 27001**: Information Security Management
- **PCI DSS**: Payment Card Industry Standards

### Security Certifications

- **OWASP API Security Top 10**: Full compliance
- **FIPS 140-2**: Cryptographic module validation
- **Common Criteria**: EAL 4+ certification
- **CSA STAR**: Level 2 attestation

### Audit Reports

Audit reports and compliance documents are available to qualified customers under NDA. Request access at:
- Email: compliance@datafoundry.com
- Portal: https://trust.datafoundry.com

---

## Support and Contact

### API Support

- **Documentation**: https://docs.datafoundry.com/api
- **Status Page**: https://status.datafoundry.com
- **Support Email**: api-support@datafoundry.com
- **Developer Slack**: https://datafoundry.slack.com

### Security Incident Reporting

For security-related issues:

- **Email**: security@datafoundry.com
- **PGP Key**: Available at https://datafoundry.com/security/pgp
- **Bug Bounty**: https://datafoundry.com/bug-bounty

### Business Hours

- **Standard Support**: 24/7
- **Premium Support**: 24/7 with 15-minute SLA
- **Emergency Response**: Immediate for critical security issues

---

**Document Classification**: Public
**Version**: 1.0.0
**Last Updated**: December 22, 2024

This API documentation is maintained in accordance with RFC 7231 (HTTP/1.1), OAuth 2.0 security best practices, and regulatory requirements for secure API design.