# Data Foundry Architecture

## Overview

Data Foundry is built as a **Service-Oriented Architecture** that separates heavy services from the lightweight application code. This design keeps the development environment fast and the deployment scalable.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client Applications                         │
│  (Web UI, Mobile Apps, API Consumers, Partner Integrations)    │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI Gateway Layer                          │
│  • Authentication & Authorization                               │
│  • Request Routing                                             │
│  • API Rate Limiting                                          │
│  • Request Validation                                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Application Core                                │
│  • Business Logic                                              │
│  • Data Models (SQLModel)                                      │
│  • Task Orchestration (Prefect)                                │
│  • AI Integration (OpenAI/Anthropic)                           │
└───────┬───────────────┬─────────────────┬───────────────────────┘
        │               │                 │
        ▼               ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   PostgreSQL    │ │      Redis      │ │   External AI   │
│ (Multi-Tenant   │ │  (Task Queue &  │ │   Services      │
│    with RLS)    │ │    Cache)       │ │ (OpenAI, Anthro)│
└─────────────────┘ └─────────────────┘ └─────────────────┘
        │               │                 │
        ▼               ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                Infrastructure Layer                             │
│  • Label Studio (Human-in-the-Loop UI)                         │
│  • Docker Containers                                           │
│  • Monitoring & Logging                                        │
└─────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. External Services (Docker Containers)

These services run as separate Docker containers to isolate resource usage:

| Service | Purpose | Container Image | Port |
|---------|---------|-----------------|------|
| PostgreSQL | Primary database with Row-Level Security (RLS) | `postgres:15-alpine` | 5432 |
| Redis | Task queue broker & cache | `redis:7-alpine` | 6379 |
| Label Studio | Human-in-the-Loop review interface | `heartexlabs/label-studio` | 8080 |
| Prefect Server | Workflow orchestration dashboard | `prefecthq/prefect:2` | 4200 |
| Prefect Agent | Task execution worker | `prefecthq/prefect:2` | - |

### 2. Application Libraries (Installed via `uv`)

These are Python packages that your code directly imports:

| Category | Libraries | Integration Point |
|----------|-----------|-------------------|
| **API Framework** | `fastapi`, `uvicorn` | Web server and routing |
| **Database ORM** | `sqlmodel`, `psycopg2` | Database operations |
| **Data Processing** | `dlt`, `pandas` | ETL pipelines |
| **AI Integration** | `openai`, `anthropic` | API-based AI services |
| **Privacy** | `presidio-analyzer`, `presidio-anonymizer` | PII detection/redaction |
| **Background Tasks** | `celery`, `prefect` | Async task processing |
| **Business Logic** | `stripe`, `pydantic` | Billing & validation |

## Data Flow Architecture

### 1. Data Ingestion Pipeline

```
Client Upload → FastAPI Endpoint → PII Redaction → Database Storage
                     │
                     ▼
              Task Queue (Redis)
                     │
                     ▼
            Background Processing
                     │
                     ▼
        AI Labeling (OpenAI/Anthropic API)
                     │
                     ▼
        Confidence Score Assessment
                     │
                     ▼
    ┌─────────────────┴─────────────────┐
    │                                   │
    ▼                                   ▼
High Confidence → Auto-approve      Low Confidence → Label Studio
```

### 2. Multi-Tenancy Implementation

```python
# Row-Level Security (RLS) ensures tenant isolation
# Each SQL query automatically filters by tenant_id

CREATE POLICY tenant_isolation ON data_records
    FOR ALL TO application_role
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

### 3. HITL (Human-in-the-Loop) Flow

```
Low Confidence Record → API Call → Label Studio → Human Review → Result → Update Database
```

## Security Architecture

### 1. Authentication & Authorization
- JWT-based authentication
- Role-based access control (RBAC)
- API key management for service accounts

### 2. Data Privacy
- **Zero-Plaintext Policy**: No raw PII/PHI stored
- **Microsoft Presidio**: Automatic PII detection and redaction
- **Data Provenance**: Every record tracked with metadata

### 3. Multi-Tenant Isolation
- **Database Level**: PostgreSQL Row-Level Security (RLS)
- **Application Level**: Tenant context validation
- **API Level**: Tenant-scoped rate limiting

## Scalability Design

### 1. Horizontal Scaling
- Stateless FastAPI instances behind load balancer
- Redis cluster for task distribution
- Database read replicas for query scaling

### 2. Background Processing
- Celery workers for CPU-intensive tasks
- Prefect for complex workflow orchestration
- Auto-scaling worker pools

### 3. API Design
- RESTful endpoints with pagination
- Async operations for long-running tasks
- WebSocket support for real-time updates

## Development vs Production

### Development Environment
```bash
# All services in Docker Compose
docker-compose up -d

# Local Python environment
source .venv/bin/activate
uvicorn src.main:app --reload
```

### Production Environment
- Managed services (AWS RDS, ElastiCache)
- Container orchestration (Kubernetes/ECS)
- CDN and reverse proxy (CloudFront/Nginx)

## Monitoring & Observability

### 1. Application Metrics
- Request latency and error rates
- Task queue depth and processing times
- AI API usage and costs

### 2. Business Metrics
- Data processing volumes
- HITL review rates
- Customer usage and billing

### 3. Infrastructure Monitoring
- Container health checks
- Database performance
- Resource utilization

## Technology Choices Rationale

### Why Docker for Services?
- **Isolation**: Prevents dependency conflicts
- **Portability**: Consistent environments
- **Scalability**: Easy container orchestration

### Why API-based AI?
- **Performance**: No local GPU requirements
- **Cost**: Pay-per-use, no idle infrastructure
- **Flexibility**: Easy model switching

### Why PostgreSQL with RLS?
- **Security**: Database-level tenant isolation
- **Performance**: Optimized for complex queries
- **Compliance**: Meets HIPAA/GDPR requirements

## Deployment Architecture

### Week 1-2: Local Development
- Docker Compose for all services
- Local PostgreSQL with RLS
- Development UI tools

### Week 3-4: Staging Environment
- Cloud-based services
- CI/CD pipeline integration
- Performance testing

### Week 5: Production Deployment
- Multi-region deployment
- Load balancing and auto-scaling
- Monitoring and alerting