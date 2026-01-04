# Spend Intelligence Dashboard - API Specification

## Overview

RESTful API for customer-level margin intelligence, anomaly detection, and peer benchmarking.

**Base URL:** `https://api.datafoundry.com/v1/analytics`

**Authentication:** Bearer JWT token (tenant_id in claims)

**Version:** 1.0.0

**Last Updated:** 2025-01-03

---

## Response Format

All API responses follow this consistent structure:

```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123xyz",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

### Meta Fields

| Field | Type | Description |
|-------|------|-------------|
| request_id | string | Unique identifier for request tracing |
| timestamp | string | ISO 8601 datetime of response |

---

## Error Codes

| HTTP Code | Name | Description |
|-----------|------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid request parameters |
| 401 | Unauthorized | Missing or invalid authentication token |
| 403 | Forbidden | Cross-tenant access attempt |
| 404 | Not Found | Resource not found |
| 422 | Validation Error | Request validation failed |
| 429 | Rate Limit Exceeded | Too many requests |
| 502 | Bad Gateway | Upstream service error (Stripe, Metering Service) |
| 503 | Service Unavailable | Service temporarily unavailable |

### Error Response Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid date range: period_end must be after period_start",
    "details": {
      "field": "period_end",
      "constraint": "must_be_after_start"
    }
  },
  "meta": {
    "request_id": "req_xyz789",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

---

## Customer Analytics Endpoints

### Get Customer Margins

Retrieves customer profitability report comparing cost-to-serve against revenue.

**Endpoint:** `GET /customers/{tenant_id}/margins`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tenant_id | string | Yes | Customer tenant identifier |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period_start | string | Yes | ISO 8601 date (start of reporting period) |
| period_end | string | Yes | ISO 8601 date (end of reporting period) |

**Request Example:**

```http
GET /v1/analytics/customers/abc123/margins?period_start=2025-01-01&period_end=2025-01-31 HTTP/1.1
Host: api.datafoundry.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response Example:**

```json
{
  "data": {
    "tenant_id": "abc123",
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "revenue": {
      "amount": 10000,
      "currency": "USD",
      "mrr": 10000
    },
    "cost_to_serve": {
      "amount": 6500,
      "currency": "USD",
      "breakdown": {
        "by_model": {
          "gpt-4": 4000,
          "gpt-3.5-turbo": 1500,
          "claude-3-opus": 1000
        },
        "by_endpoint": {
          "/chat": 5000,
          "/summarize": 1500
        }
      }
    },
    "margin": {
      "amount": 3500,
      "percentage": 35.0
    },
    "status": "profitable"
  },
  "meta": {
    "request_id": "req_margin_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| tenant_id | string | Customer identifier |
| period | object | Reporting period start/end dates |
| revenue | object | Revenue metrics (amount, currency, MRR) |
| cost_to_serve | object | Total cost with breakdowns |
| margin | object | Margin amount and percentage |
| status | string | Profitability status (profitable/breakeven/loss) |

---

### Get Customer Costs

Retrieves detailed cost breakdown for a customer.

**Endpoint:** `GET /customers/{tenant_id}/costs`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tenant_id | string | Yes | Customer tenant identifier |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period_start | string | Yes | ISO 8601 date |
| period_end | string | Yes | ISO 8601 date |
| group_by | string | No | Group results by: model, endpoint, date (default: model) |

**Request Example:**

```http
GET /v1/analytics/customers/abc123/costs?period_start=2025-01-01&period_end=2025-01-31&group_by=model HTTP/1.1
Authorization: Bearer <jwt_token>
```

**Response Example:**

```json
{
  "data": {
    "tenant_id": "abc123",
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "total_cost": {
      "amount": 6500,
      "currency": "USD"
    },
    "breakdown": [
      {
        "dimension": "model",
        "value": "gpt-4",
        "cost": {
          "amount": 4000,
          "currency": "USD",
          "percentage_of_total": 61.5
        },
        "usage": {
          "input_tokens": 500000,
          "output_tokens": 300000,
          "requests": 1500
        }
      },
      {
        "dimension": "model",
        "value": "gpt-3.5-turbo",
        "cost": {
          "amount": 1500,
          "currency": "USD",
          "percentage_of_total": 23.1
        },
        "usage": {
          "input_tokens": 2000000,
          "output_tokens": 800000,
          "requests": 5000
        }
      }
    ]
  },
  "meta": {
    "request_id": "req_cost_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

---

### Get Customer Revenue

Retrieves Stripe revenue data for a customer.

**Endpoint:** `GET /customers/{tenant_id}/revenue`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tenant_id | string | Yes | Customer tenant identifier |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period_start | string | Yes | ISO 8601 date |
| period_end | string | Yes | ISO 8601 date |

**Request Example:**

```http
GET /v1/analytics/customers/abc123/revenue?period_start=2025-01-01&period_end=2025-01-31 HTTP/1.1
Authorization: Bearer <jwt_token>
```

**Response Example:**

```json
{
  "data": {
    "tenant_id": "abc123",
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "revenue": {
      "total": {
        "amount": 10000,
        "currency": "USD"
      },
      "mrr": {
        "amount": 10000,
        "currency": "USD"
      },
      "arr": {
        "amount": 120000,
        "currency": "USD"
      },
      "breakdown": {
        "subscription": {
          "amount": 9000,
          "currency": "USD"
        },
        "usage_fees": {
          "amount": 1000,
          "currency": "USD"
        }
      }
    },
    "subscription": {
      "id": "sub_abc123",
      "status": "active",
      "tier": "growth",
      "current_period_start": "2025-01-01T00:00:00Z",
      "current_period_end": "2025-02-01T00:00:00Z"
    }
  },
  "meta": {
    "request_id": "req_revenue_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

---

## Anomaly Detection Endpoints

### Get Anomalies

Returns list of detected anomalies for a customer.

**Endpoint:** `GET /anomalies/{tenant_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tenant_id | string | Yes | Customer tenant identifier |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period_start | string | Yes | ISO 8601 date |
| period_end | string | Yes | ISO 8601 date |
| severity | string | No | Filter by: low, medium, high (default: all) |
| type | string | No | Filter by type: usage_spike, margin_compression, cost_spike, revenue_drop |

**Request Example:**

```http
GET /v1/analytics/anomalies/abc123?period_start=2025-01-01&period_end=2025-01-31&severity=high HTTP/1.1
Authorization: Bearer <jwt_token>
```

**Response Example:**

```json
{
  "data": {
    "tenant_id": "abc123",
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "anomalies": [
      {
        "id": "anom_123",
        "type": "usage_spike",
        "severity": "high",
        "description": "Usage increased 150% vs baseline",
        "detected_at": "2025-01-15T10:30:00Z",
        "baseline_value": 1000,
        "current_value": 2500,
        "deviation_percent": 150,
        "suggested_action": "Investigate potential abuse or pricing misalignment",
        "related_metrics": {
          "endpoint": "/chat",
          "model": "gpt-4"
        }
      },
      {
        "id": "anom_124",
        "type": "margin_compression",
        "severity": "medium",
        "description": "Margin dropped 10% vs baseline",
        "detected_at": "2025-01-20T14:00:00Z",
        "baseline_value": 35.0,
        "current_value": 31.5,
        "deviation_percent": -10,
        "suggested_action": "Review cost structure and pricing"
      }
    ],
    "summary": {
      "total_count": 2,
      "by_severity": {
        "high": 1,
        "medium": 1,
        "low": 0
      },
      "by_type": {
        "usage_spike": 1,
        "margin_compression": 1
      }
    }
  },
  "meta": {
    "request_id": "req_anomaly_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

**Anomaly Types:**

| Type | Description |
|------|-------------|
| usage_spike | Unusual increase in API usage |
| margin_compression | Margin % decline vs baseline |
| cost_spike | Unexpected cost increase |
| revenue_drop | Revenue decline warning |

**Severity Levels:**

| Level | Threshold |
|-------|-----------|
| high | >50% deviation |
| medium | 25-50% deviation |
| low | 10-25% deviation |

---

### Configure Alerts

Sets up alert thresholds for anomaly notifications.

**Endpoint:** `POST /alerts/configure`

**Request Body:**

```json
{
  "tenant_id": "abc123",
  "alert_config": {
    "enabled": true,
    "channels": [
      {
        "type": "slack",
        "webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ"
      },
      {
        "type": "email",
        "recipients": ["ops@example.com"]
      }
    ],
    "thresholds": {
      "usage_spike": {
        "enabled": true,
        "severity": "high",
        "deviation_percent": 50
      },
      "margin_compression": {
        "enabled": true,
        "severity": "medium",
        "deviation_percent": 10
      },
      "cost_spike": {
        "enabled": true,
        "severity": "high",
        "deviation_percent": 40
      },
      "revenue_drop": {
        "enabled": false,
        "severity": "high",
        "deviation_percent": 20
      }
    }
  }
}
```

**Response Example:**

```json
{
  "data": {
    "config_id": "config_abc123",
    "tenant_id": "abc123",
    "status": "active",
    "created_at": "2025-01-03T10:30:00Z",
    "channels_configured": 2,
    "thresholds_configured": 3
  },
  "meta": {
    "request_id": "req_alert_config_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

**Request Validation:**

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| tenant_id | string | Yes | Must match JWT token |
| enabled | boolean | Yes | true/false |
| channels | array | Yes | At least one channel |
| channels[].type | string | Yes | slack or email |
| thresholds | object | Yes | At least one threshold enabled |
| thresholds[].enabled | boolean | Yes | true/false |
| thresholds[].deviation_percent | number | Yes | 1-100 |

---

## Benchmarking Endpoints

### Get Customer Benchmarks

Returns peer comparison metrics for a customer.

**Endpoint:** `GET /benchmarks/{tenant_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tenant_id | string | Yes | Customer tenant identifier |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period_start | string | Yes | ISO 8601 date |
| period_end | string | Yes | ISO 8601 date |
| peer_group | string | No | Filter by: tier, industry, region (default: tier) |

**Request Example:**

```http
GET /v1/analytics/benchmarks/abc123?period_start=2025-01-01&period_end=2025-01-31&peer_group=tier HTTP/1.1
Authorization: Bearer <jwt_token>
```

**Response Example:**

```json
{
  "data": {
    "tenant_id": "abc123",
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "peer_group": {
      "type": "tier",
      "name": "growth"
    },
    "your_metrics": {
      "margin_percentage": 35.0,
      "cost_per_customer": 6500,
      "revenue_per_customer": 10000,
      "usage_per_request": 0.65
    },
    "peer_percentiles": {
      "margin_percentage": {
        "25th": 25.0,
        "50th": 45.0,
        "75th": 65.0
      },
      "cost_per_customer": {
        "25th": 3000,
        "50th": 5000,
        "75th": 8000
      },
      "revenue_per_customer": {
        "25th": 5000,
        "50th": 10000,
        "75th": 15000
      }
    },
    "your_percentile_rank": {
      "margin_percentage": 35,
      "cost_per_customer": 60,
      "revenue_per_customer": 50
    },
    "anonymized_customer_count": 42,
    "insights": [
      {
        "metric": "margin_percentage",
        "message": "Your margin is below median for Growth tier customers"
      },
      {
        "metric": "cost_per_customer",
        "message": "Your costs are in the top quartile, consider optimization"
      }
    ]
  },
  "meta": {
    "request_id": "req_benchmark_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

**Privacy Note:** All peer data is anonymized. No customer-identifiable information is exposed.

---

### Get Platform Percentiles

Returns platform-wide percentile distributions (admin dashboard).

**Endpoint:** `GET /percentiles`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period_start | string | Yes | ISO 8601 date |
| period_end | string | Yes | ISO 8601 date |
| metrics | string | Yes | Comma-separated list: margin_percentage, cost_per_customer |

**Request Example:**

```http
GET /v1/analytics/percentiles?period_start=2025-01-01&period_end=2025-01-31&metrics=margin_percentage,cost_per_customer HTTP/1.1
Authorization: Bearer <admin_jwt_token>
```

**Response Example:**

```json
{
  "data": {
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "total_customers": 150,
    "percentiles": {
      "margin_percentage": {
        "10th": 15.0,
        "25th": 25.0,
        "50th": 45.0,
        "75th": 65.0,
        "90th": 80.0
      },
      "cost_per_customer": {
        "10th": 1500,
        "25th": 3000,
        "50th": 5000,
        "75th": 8000,
        "90th": 12000
      }
    }
  },
  "meta": {
    "request_id": "req_percentiles_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

**Authorization:** Requires admin-tier JWT token.

---

## Alert Management Endpoints

### Test Alert Configuration

Sends a test alert to configured channels.

**Endpoint:** `POST /alerts/test`

**Request Body:**

```json
{
  "tenant_id": "abc123",
  "channel": "slack",
  "alert_type": "margin_compression"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| tenant_id | string | Yes | Customer tenant ID |
| channel | string | Yes | Target channel: slack, email |
| alert_type | string | Yes | Alert type to test: usage_spike, margin_compression, cost_spike, revenue_drop |

**Response Example:**

```json
{
  "data": {
    "test_alert_id": "test_abc123",
    "tenant_id": "abc123",
    "status": "sent",
    "delivered_at": "2025-01-03T10:30:00Z",
    "channel": "slack",
    "message": "Test alert sent to Slack successfully"
  },
  "meta": {
    "request_id": "req_test_alert_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

**Test Alert Content:**

The test alert sends a sample anomaly notification to verify channel configuration.

---

### Get Alert History

Retrieves historical alerts for a customer.

**Endpoint:** `GET /alerts/history/{tenant_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tenant_id | string | Yes | Customer tenant identifier |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| period_start | string | Yes | ISO 8601 date |
| period_end | string | Yes | ISO 8601 date |
| status | string | No | Filter: acknowledged, pending, dismissed |

**Request Example:**

```http
GET /v1/analytics/alerts/history/abc123?period_start=2025-01-01&period_end=2025-01-31&status=pending HTTP/1.1
Authorization: Bearer <jwt_token>
```

**Response Example:**

```json
{
  "data": {
    "tenant_id": "abc123",
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "alerts": [
      {
        "id": "alert_123",
        "anomaly_id": "anom_123",
        "type": "usage_spike",
        "severity": "high",
        "triggered_at": "2025-01-15T10:30:00Z",
        "delivered_via": ["slack", "email"],
        "status": "acknowledged",
        "acknowledged_at": "2025-01-15T11:00:00Z",
        "acknowledged_by": "user_456",
        "notes": "Investigating - appears to be legitimate growth"
      },
      {
        "id": "alert_124",
        "anomaly_id": "anom_124",
        "type": "margin_compression",
        "severity": "medium",
        "triggered_at": "2025-01-20T14:00:00Z",
        "delivered_via": ["slack"],
        "status": "pending",
        "acknowledged_at": null,
        "acknowledged_by": null,
        "notes": null
      }
    ],
    "summary": {
      "total_count": 2,
      "by_status": {
        "acknowledged": 1,
        "pending": 1,
        "dismissed": 0
      }
    }
  },
  "meta": {
    "request_id": "req_alert_history_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

**Alert Status Values:**

| Status | Description |
|--------|-------------|
| pending | Alert delivered, not yet acknowledged |
| acknowledged | User has seen and acknowledged |
| dismissed | User dismissed as false positive |

---

### Acknowledge Alert

Marks an alert as acknowledged.

**Endpoint:** `PATCH /alerts/{alert_id}/acknowledge`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| alert_id | string | Yes | Alert identifier |

**Request Body:**

```json
{
  "notes": "Investigating - appears to be legitimate growth"
}
```

**Response Example:**

```json
{
  "data": {
    "alert_id": "alert_123",
    "status": "acknowledged",
    "acknowledged_at": "2025-01-15T11:00:00Z",
    "acknowledged_by": "user_456",
    "notes": "Investigating - appears to be legitimate growth"
  },
  "meta": {
    "request_id": "req_ack_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

---

## Authentication

### JWT Token Format

All requests require a Bearer JWT token in the Authorization header.

**Header:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Token Payload:**

```json
{
  "user_id": "user_123",
  "tenant_id": "tenant_456",
  "email": "user@example.com",
  "tier": "growth",
  "roles": ["customer", "analyst"],
  "exp": 1704067200,
  "iat": 1704066300,
  "iss": "https://auth.datafoundry.com"
}
```

**Required Claims:**

| Claim | Type | Description |
|-------|------|-------------|
| user_id | string | Unique user identifier |
| tenant_id | string | Customer tenant ID |
| tier | string | Subscription tier (starter/growth/professional) |
| exp | integer | Token expiration timestamp |
| iat | integer | Token issued at timestamp |

### Tenant Isolation

All endpoints enforce strict tenant_id isolation:

- Token's tenant_id must match requested tenant_id in path
- Cross-tenant requests return 403 Forbidden
- Admin tokens can access all tenants (for /percentiles endpoint)

**Example Error Response (Cross-tenant):**

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Token tenant_id (tenant_456) does not match requested tenant_id (tenant_789)"
  },
  "meta": {
    "request_id": "req_xyz789",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

---

## Rate Limiting

### Tier-Based Limits

Rate limits are enforced per tenant based on subscription tier.

| Tier | Requests/Minute | Requests/Day |
|------|-----------------|--------------|
| Starter | 60 | 1,000 |
| Growth | 600 | 10,000 |
| Professional | 6,000 | 100,000 |

### Rate Limit Headers

All API responses include rate limit information:

```http
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 599
X-RateLimit-Reset: 1704067200
```

**Header Descriptions:**

| Header | Description |
|--------|-------------|
| X-RateLimit-Limit | Total requests allowed in current window |
| X-RateLimit-Remaining | Requests remaining in current window |
| X-RateLimit-Reset | Unix timestamp when window resets |

### Rate Limit Exceeded Response

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 30 seconds.",
    "retry_after": 30
  },
  "meta": {
    "request_id": "req_rate_limit_001",
    "timestamp": "2025-01-03T10:30:00Z"
  }
}
```

---

## Data Schemas

### Margin Response Schema

```typescript
interface MarginResponse {
  data: {
    tenant_id: string;
    period: {
      start: string;  // ISO 8601
      end: string;    // ISO 8601
    };
    revenue: {
      amount: number;
      currency: string;
      mrr: number;
    };
    cost_to_serve: {
      amount: number;
      currency: string;
      breakdown: {
        by_model: Record<string, number>;
        by_endpoint: Record<string, number>;
      };
    };
    margin: {
      amount: number;
      percentage: number;
    };
    status: 'profitable' | 'breakeven' | 'loss';
  };
  meta: Meta;
}
```

### Anomaly Response Schema

```typescript
interface AnomalyResponse {
  data: {
    tenant_id: string;
    period: {
      start: string;
      end: string;
    };
    anomalies: Anomaly[];
    summary: {
      total_count: number;
      by_severity: Record<string, number>;
      by_type: Record<string, number>;
    };
  };
  meta: Meta;
}

interface Anomaly {
  id: string;
  type: 'usage_spike' | 'margin_compression' | 'cost_spike' | 'revenue_drop';
  severity: 'low' | 'medium' | 'high';
  description: string;
  detected_at: string;
  baseline_value: number;
  current_value: number;
  deviation_percent: number;
  suggested_action: string;
  related_metrics?: {
    endpoint?: string;
    model?: string;
  };
}
```

### Benchmark Response Schema

```typescript
interface BenchmarkResponse {
  data: {
    tenant_id: string;
    period: {
      start: string;
      end: string;
    };
    peer_group: {
      type: 'tier' | 'industry' | 'region';
      name: string;
    };
    your_metrics: Record<string, number>;
    peer_percentiles: Record<string, {
      '25th': number;
      '50th': number;
      '75th': number;
    }>;
    your_percentile_rank: Record<string, number>;
    anonymized_customer_count: number;
    insights: Array<{
      metric: string;
      message: string;
    }>;
  };
  meta: Meta;
}
```

---

## SDK Examples

### Python SDK

```python
import requests
from datetime import datetime

class SpendIntelligenceClient:
    def __init__(self, api_key: str, base_url: str = "https://api.datafoundry.com/v1/analytics"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def get_customer_margins(self, tenant_id: str, period_start: str, period_end: str) -> dict:
        """Get customer profitability report."""
        response = self.session.get(
            f"{self.base_url}/customers/{tenant_id}/margins",
            params={"period_start": period_start, "period_end": period_end}
        )
        response.raise_for_status()
        return response.json()

    def get_anomalies(self, tenant_id: str, period_start: str, period_end: str, severity: str = None) -> dict:
        """Get detected anomalies for a customer."""
        params = {"period_start": period_start, "period_end": period_end}
        if severity:
            params["severity"] = severity

        response = self.session.get(
            f"{self.base_url}/anomalies/{tenant_id}",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def get_benchmarks(self, tenant_id: str, period_start: str, period_end: str, peer_group: str = "tier") -> dict:
        """Get peer comparison metrics."""
        response = self.session.get(
            f"{self.base_url}/benchmarks/{tenant_id}",
            params={
                "period_start": period_start,
                "period_end": period_end,
                "peer_group": peer_group
            }
        )
        response.raise_for_status()
        return response.json()

# Usage example
client = SpendIntelligenceClient(api_key="your_jwt_token")

# Get customer margins
margins = client.get_customer_margins(
    tenant_id="abc123",
    period_start="2025-01-01",
    period_end="2025-01-31"
)
print(f"Margin: {margins['data']['margin']['percentage']}%")

# Get high-severity anomalies
anomalies = client.get_anomalies(
    tenant_id="abc123",
    period_start="2025-01-01",
    period_end="2025-01-31",
    severity="high"
)
print(f"Found {len(anomalies['data']['anomalies'])} high-severity anomalies")

# Get benchmarks
benchmarks = client.get_benchmarks(
    tenant_id="abc123",
    period_start="2025-01-01",
    period_end="2025-01-31"
)
percentile = benchmarks['data']['your_percentile_rank']['margin_percentage']
print(f"Margin percentile rank: {percentile}%")
```

### cURL Examples

```bash
# Get customer margins
curl -X GET \
  'https://api.datafoundry.com/v1/analytics/customers/abc123/margins?period_start=2025-01-01&period_end=2025-01-31' \
  -H "Authorization: Bearer ${JWT_TOKEN}"

# Get anomalies with severity filter
curl -X GET \
  'https://api.datafoundry.com/v1/analytics/anomalies/abc123?period_start=2025-01-01&period_end=2025-01-31&severity=high' \
  -H "Authorization: Bearer ${JWT_TOKEN}"

# Get benchmarks
curl -X GET \
  'https://api.datafoundry.com/v1/analytics/benchmarks/abc123?period_start=2025-01-01&period_end=2025-01-31&peer_group=tier' \
  -H "Authorization: Bearer ${JWT_TOKEN}"

# Configure alerts
curl -X POST \
  https://api.datafoundry.com/v1/analytics/alerts/configure \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "abc123",
    "alert_config": {
      "enabled": true,
      "channels": [
        {
          "type": "slack",
          "webhook_url": "https://hooks.slack.com/services/XXX/YYY/ZZZ"
        }
      ],
      "thresholds": {
        "usage_spike": {
          "enabled": true,
          "severity": "high",
          "deviation_percent": 50
        }
      }
    }
  }'

# Test alert
curl -X POST \
  https://api.datafoundry.com/v1/analytics/alerts/test \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "abc123",
    "channel": "slack",
    "alert_type": "margin_compression"
  }'

# Acknowledge alert
curl -X PATCH \
  https://api.datafoundry.com/v1/analytics/alerts/alert_123/acknowledge \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "notes": "Investigating - appears to be legitimate growth"
  }'
```

### JavaScript/TypeScript SDK

```typescript
interface SpendIntelligenceConfig {
  apiKey: string;
  baseUrl?: string;
}

class SpendIntelligenceClient {
  private baseUrl: string;
  private headers: HeadersInit;

  constructor(config: SpendIntelligenceConfig) {
    this.baseUrl = config.baseUrl || 'https://api.datafoundry.com/v1/analytics';
    this.headers = {
      'Authorization': `Bearer ${config.apiKey}`,
      'Content-Type': 'application/json',
    };
  }

  async getCustomerMargins(
    tenantId: string,
    periodStart: string,
    periodEnd: string
  ): Promise<MarginResponse> {
    const url = new URL(`${this.baseUrl}/customers/${tenantId}/margins`);
    url.searchParams.set('period_start', periodStart);
    url.searchParams.set('period_end', periodEnd);

    const response = await fetch(url.toString(), { headers: this.headers });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getAnomalies(
    tenantId: string,
    periodStart: string,
    periodEnd: string,
    severity?: string
  ): Promise<AnomalyResponse> {
    const url = new URL(`${this.baseUrl}/anomalies/${tenantId}`);
    url.searchParams.set('period_start', periodStart);
    url.searchParams.set('period_end', periodEnd);
    if (severity) url.searchParams.set('severity', severity);

    const response = await fetch(url.toString(), { headers: this.headers });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getBenchmarks(
    tenantId: string,
    periodStart: string,
    periodEnd: string,
    peerGroup: string = 'tier'
  ): Promise<BenchmarkResponse> {
    const url = new URL(`${this.baseUrl}/benchmarks/${tenantId}`);
    url.searchParams.set('period_start', periodStart);
    url.searchParams.set('period_end', periodEnd);
    url.searchParams.set('peer_group', peerGroup);

    const response = await fetch(url.toString(), { headers: this.headers });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}

// Usage example
const client = new SpendIntelligenceClient({
  apiKey: 'your_jwt_token'
});

const margins = await client.getCustomerMargins(
  'abc123',
  '2025-01-01',
  '2025-01-31'
);
console.log(`Margin: ${margins.data.margin.percentage}%`);
```

---

## Best Practices

### Request Optimization

1. **Batch Period Requests:** Query the widest practical date range to minimize API calls
2. **Cache Results:** Client-side cache margin/cost data for 1 hour
3. **Use Severity Filters:** Filter anomalies by severity to reduce response size

### Error Handling

```python
def get_with_retry(client, endpoint, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.get(endpoint)
            if response.status_code == 429:
                # Rate limited - wait and retry
                retry_after = response.headers.get('Retry-After', 30)
                time.sleep(int(retry_after))
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
```

### Monitoring

- Log all `request_id` values from responses for debugging
- Monitor rate limit headers to avoid throttling
- Set up alerts for 502 errors (upstream service issues)

---

## Changelog

### v1.0.0 (2025-01-03)
- Initial release with 9 analytics endpoints
- Customer analytics: margins, costs, revenue (3 endpoints)
- Anomaly detection: list anomalies, configure alerts (2 endpoints)
- Peer benchmarking: customer benchmarks, platform percentiles (2 endpoints)
- Alert management: test alert, alert history, acknowledge alert (3 endpoints)
- JWT-based authentication with tenant isolation
- Tier-based rate limiting
- Python, cURL, and TypeScript SDK examples

---

## Support

**Documentation:** https://docs.datafoundry.com/analytics
**Issues:** analytics-support@datafoundry.com
**Status Page:** https://status.datafoundry.com

---

## Appendix A: Endpoint Summary

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/customers/{tenant_id}/margins` | Get customer profitability | Customer |
| GET | `/customers/{tenant_id}/costs` | Get cost breakdown | Customer |
| GET | `/customers/{tenant_id}/revenue` | Get revenue data | Customer |
| GET | `/anomalies/{tenant_id}` | List detected anomalies | Customer |
| POST | `/alerts/configure` | Configure alert thresholds | Customer |
| GET | `/benchmarks/{tenant_id}` | Get peer benchmarks | Customer |
| GET | `/percentiles` | Get platform percentiles | Admin |
| POST | `/alerts/test` | Test alert delivery | Customer |
| GET | `/alerts/history/{tenant_id}` | Get alert history | Customer |
| PATCH | `/alerts/{alert_id}/acknowledge` | Acknowledge alert | Customer |

---

## Appendix B: HTTP Status Codes

| Code | Name | Common Causes |
|------|------|---------------|
| 200 | OK | Successful request |
| 400 | Bad Request | Invalid query parameters, malformed JSON |
| 401 | Unauthorized | Missing/invalid token, expired token |
| 403 | Forbidden | Cross-tenant access, insufficient permissions |
| 404 | Not Found | Invalid tenant_id, non-existent alert |
| 422 | Validation Error | Date range invalid, missing required fields |
| 429 | Rate Limit Exceeded | Too many requests |
| 502 | Bad Gateway | Stripe/Metering Service unavailable |
| 503 | Service Unavailable | API maintenance, temporary outage |

---

## Appendix C: Rate Limit Calculator

Use this formula to calculate safe request rates:

```
requests_per_minute = tier_limit
requests_per_second = requests_per_minute / 60
recommended_interval = 60 / requests_per_minute
```

**Example (Growth Tier):**
- Limit: 600 requests/minute
- Safe rate: 10 requests/second
- Recommended interval: 0.1 seconds between requests

**For Batch Operations:**
```
total_time_seconds = (total_requests / tier_limit) * 60
```

---

**Document Version:** 1.0.0
**Last Updated:** 2025-01-03
**API Base URL:** https://api.datafoundry.com/v1/analytics
