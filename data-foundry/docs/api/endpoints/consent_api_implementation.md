# Consent API Implementation Documentation

## Overview

This document describes the implementation of the GDPR-compliant consent management API for Data Foundry. The API provides endpoints for managing user consent following OpenAPI 3.0 specifications and REST principles.

## Architecture

The consent API follows a layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                      │
├─────────────────────────────────────────────────────────────┤
│              Contract-First Design (Pydantic)               │
├─────────────────────────────────────────────────────────────┤
│              Business Logic (ConsentManager)                │
├─────────────────────────────────────────────────────────────┤
│            Data Access (DatabaseManager)                    │
├─────────────────────────────────────────────────────────────┤
│              Audit Service (GDPR Compliance)                │
└─────────────────────────────────────────────────────────────┘
```

## API Endpoints

### 1. Grant Consent
- **Endpoint**: `POST /api/v1/consent/grant`
- **Purpose**: Record new consent according to GDPR Article 7
- **GDPR Requirements**:
  - Consent must be specific, informed, and unambiguous
  - Minimum 50 characters for consent text
  - Must explain data processing details
  - IP address and user agent recorded for audit

### 2. Withdraw Consent
- **Endpoint**: `POST /api/v1/consent/withdraw`
- **Purpose**: Implement right to withdraw consent (GDPR Article 7(3))
- **Features**:
  - As easy as giving consent
  - Immediate effect
  - Previous processing remains lawful

### 3. Verify Consent
- **Endpoint**: `GET /api/v1/consent/verify/{user_id}/{consent_type}`
- **Purpose**: Check active consent status
- **Use Cases**:
  - Pre-processing checks
  - Consent-gated features
  - Permission validation

### 4. Object to Processing
- **Endpoint**: `POST /api/v1/consent/object`
- **Purpose**: GDPR Article 21 objection to processing
- **Features**:
  - Can object without prior consent
  - Legally binding record
  - Processing must stop upon objection

### 5. Get User Consents
- **Endpoint**: `GET /api/v1/consent/user/{user_id}`
- **Purpose**: Retrieve user's current consents
- **Use Cases**:
  - User preference centers
  - Compliance reporting

### 6. Get Consent History
- **Endpoint**: `GET /api/v1/consent/user/{user_id}/history`
- **Purpose**: Complete audit trail of consent activities
- **Features**:
  - Paginated results
  - Full metadata
  - GDPR audit requirements

## Implementation Details

### Contract-First Design

The API follows a contract-first approach using OpenAPI 3.0 specifications:

1. **Contracts Defined First**: All request/response models defined in `contracts.py`
2. **Validation**: Pydantic models ensure data integrity
3. **Documentation**: Auto-generated OpenAPI docs
4. **Type Safety**: End-to-end TypeScript-like safety

### Rate Limiting

Simple in-memory rate limiting protects against abuse:
- 100 requests per hour per user
- Separate limits per endpoint type
- Graceful degradation when limits exceeded

### Error Handling

Consistent error responses across all endpoints:
- 400: Validation errors
- 401: Authentication required
- 404: Resource not found
- 429: Rate limit exceeded
- 500: Server errors

### Security Features

1. **Authentication**: JWT token-based auth
2. **IP Hashing**: Privacy protection for audit logs
3. **Input Validation**: Comprehensive request validation
4. **SQL Injection Prevention**: Parameterized queries
5. **Audit Trail**: Complete logging of all actions

## GDPR Compliance

### Article 7 - Conditions for Consent
- ✅ Freely given
- ✅ Specific and informed
- ✅ Unambiguous indication of wishes
- ✅ Demonstrable record-keeping
- ✅ Right to withdraw

### Article 21 - Right to Object
- ✅ Objection to processing
- ✅ Legal basis respected
- ✅ No prior consent required
- ✅ Immediate effect

### Data Protection
- ✅ IP address hashing
- ✅ Minimal data collection
- ✅ Purpose limitation
- ✅ Retention policies
- ✅ Audit trails

## Database Schema

The consent records are stored with the following structure:

```sql
CREATE TABLE consent_records (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    consent_type VARCHAR(100) NOT NULL,
    consent_text TEXT NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(255) NOT NULL,
    user_agent TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    withdrawn_at TIMESTAMPTZ,
    consent_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_consent_user_type ON consent_records(user_id, consent_type);
CREATE INDEX idx_consent_status ON consent_records(status);
CREATE INDEX idx_consent_granted_at ON consent_records(granted_at);
```

## Testing

Comprehensive test suite includes:
- Unit tests for business logic
- Integration tests for endpoints
- GDPR compliance validation
- Rate limiting verification
- Error scenario coverage

Run tests with:
```bash
pytest tests/api/test_consent_endpoints.py -v
```

## API Usage Examples

### Granting Consent

```python
import requests

# Get auth token
token_response = requests.get("http://localhost:8000/test-token")
token = token_response.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}

# Grant consent
consent_data = {
    "user_id": "user_12345",
    "consent_type": "data_processing",
    "consent_text": "I consent to the processing of my personal data for service improvement. This includes analysis of usage patterns and storage for 2 years.",
    "metadata": {
        "ip": "192.168.1.100",
        "user_agent": "Mozilla/5.0 (Test Browser)",
        "purpose": "service_improvement",
        "retention_period": "2_years"
    }
}

response = requests.post(
    "http://localhost:8000/api/v1/consent/grant",
    json=consent_data,
    headers=headers
)

print(response.json())
```

### Verifying Consent

```python
# Check if user has consent
response = requests.get(
    "http://localhost:8000/api/v1/consent/verify/user_12345/data_processing",
    headers=headers
)

result = response.json()
if result["has_consent"]:
    print("User has active consent")
else:
    print("No active consent found")
```

### Withdrawing Consent

```python
withdraw_data = {
    "user_id": "user_12345",
    "consent_type": "data_processing",
    "reason": "No longer wish to participate",
    "metadata": {
        "ip": "192.168.1.100",
        "user_agent": "Mozilla/5.0 (Test Browser)"
    }
}

response = requests.post(
    "http://localhost:8000/api/v1/consent/withdraw",
    json=withdraw_data,
    headers=headers
)
```

## Monitoring and Logging

### Audit Events
All consent operations are logged with:
- User identifier
- Action performed
- Timestamp
- IP address (hashed)
- Consent details
- Metadata

### Metrics to Monitor
- Consent grant rate
- Consent withdrawal rate
- Verification requests
- Objection filings
- API response times
- Error rates

## Performance Considerations

1. **Database Indexes**: Optimized for common query patterns
2. **Caching**: Frequently accessed consent records
3. **Pagination**: Large result sets efficiently handled
4. **Async Operations**: Non-blocking database calls
5. **Connection Pooling**: Database connections reused

## Future Enhancements

1. **Advanced Rate Limiting**: Redis-based distributed limiting
2. **Consent Templates**: Pre-defined consent texts
3. **Bulk Operations**: Batch consent management
4. **Webhooks**: Real-time consent notifications
5. **Analytics**: Consent trends and insights
6. **Multi-tenant**: Tenant-specific consent policies

## Integration Guide

### Frontend Integration
1. Include JWT token in Authorization header
2. Handle rate limiting (429) responses
3. Display consent details clearly
4. Provide easy withdrawal mechanism
5. Show consent history to users

### Backend Integration
1. Call verify endpoint before processing
2. Handle objections immediately
3. Log all consent-dependent operations
4. Implement consent expiry checking
5. Respect user preferences

## Compliance Checklist

- [x] Specific, informed, unambiguous consent
- [x] Easy withdrawal mechanism
- [x] Complete audit trail
- [x] IP address hashing for privacy
- [x] Objection handling (Article 21)
- [x] Record-keeping requirements
- [x] Data minimization
- [x] Purpose limitation
- [x] Retention policies

## Support

For questions or issues:
- Create issue in project repository
- Review OpenAPI specification at `/docs`
- Check audit logs for troubleshooting
- Contact privacy@datafoundry.com for compliance questions