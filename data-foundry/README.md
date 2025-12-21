# Data Foundry - Enrichment-as-a-Service (EaaS) Platform

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**AI-powered data cleaning and labeling platform with Human-in-the-Loop verification** - Built for Healthcare, Finance, and E-commerce industries.

## 🚀 What is Data Foundry?

Data Foundry is a comprehensive **Enrichment-as-a-Service** platform that transforms raw data into high-quality, annotated datasets through a multi-stage refinery process. It combines AI automation with human expertise to ensure data accuracy and compliance.

### Core Workflow

1. **📥 Data Ingestion** - Secure, tenant-isolated data intake
2. **🔒 Privacy Protection** - Automatic PII/PHI redaction using Microsoft Presidio
3. **🤖 AI-Powered Labeling** - Smart classification with OpenAI/Anthropic models
4. **👥 Human-in-the-Loop** - Expert review for low-confidence predictions
5. **📊 Quality Assurance** - Confidence scoring and routing logic
6. **💰 Metered Billing** - Usage tracking with Stripe integration

## 🏗️ Architecture Overview

```mermaid
graph TB
    subgraph "Client Layer"
        A[Web Apps]
        B[Mobile Apps]
        C[API Clients]
    end

    subgraph "API Gateway"
        D[FastAPI API]
        E[Auth & AuthZ]
        F[Rate Limiting]
        G[Request Logs]
    end

    subgraph "Core Services"
        H[PostgreSQL<br/><i>Multi-tenant</i>]
        I[Row-Level Security<br/><i>RLS</i>]
        J[Audit Logs]
    end

    subgraph "Supporting Services"
        K[Label Studio<br/><i>Human Review</i>]
        L[Annotation UI]
        M[Project Management]
        N[Prefect<br/><i>Orchestration</i>]
        O[Workflows]
        P[Monitoring]
        Q[Redis<br/><i>Caching & Queue</i>]
        R[Session Store]
    end

    A --> D
    B --> D
    C --> D

    D --> E
    D --> F
    D --> G

    E --> H
    F --> H
    G --> H

    H --> I
    H --> J

    D --> K
    D --> N
    D --> Q

    K --> L
    K --> M

    N --> O
    N --> P

    Q --> R

    style D fill:#e1f5fe
    style H fill:#f3e5f5
    style K fill:#fff3e0
    style N fill:#e8f5e9
    style Q fill:#fce4ec
```

## 🛠️ Technology Stack

### Core Framework
- **API Server**: FastAPI with async/await support
- **Database ORM**: SQLModel (Pydantic + SQLAlchemy)
- **Configuration**: Pydantic Settings with environment variable support
- **Package Manager**: UV for fast dependency management

### Data Processing
- **ELT Pipeline**: dlt (Data Load Tool) for scalable data processing
- **Orchestration**: Prefect for workflow management and monitoring
- **Task Queue**: Redis for background job processing
- **DataFrames**: Pandas for in-memory data manipulation

### AI & Machine Learning
- **AI Models**: LiteLLM unified API with OpenRouter (100+ models: OpenAI, Anthropic, Google, Mistral, Cohere, etc.)
- **Cost Optimization**: Real-time cost calculation with volume tiering and provider switching
- **Privacy**: Microsoft Presidio for PII/PHI detection and redaction
- **Confidence Scoring**: Custom logic for AI prediction reliability with logprob extraction
- **Fallback Chain**: Automatic model/provider fallback with exponential backoff retry logic
- **Optional**: Refuel Autolabel integration for orchestration & quality validation

### Human-in-the-Loop
- **Annotation Platform**: Label Studio for expert review
- **Workflow Management**: Queue-based routing for human verification
- **Quality Control**: Multi-reviewer consensus mechanisms

### Security & Compliance
- **Authentication**: JWT tokens with tenant context
- **Multi-tenancy**: PostgreSQL Row-Level Security (RLS)
- **Privacy**: HIPAA/GDPR-compliant data handling
- **Audit**: Complete activity logging for compliance

### Business Operations
- **Billing**: Stripe metered billing integration
- **Monitoring**: Request logging and performance metrics
- **Documentation**: Auto-generated OpenAPI/Swagger docs

## 🚀 Quick Start

### Prerequisites

- Python 3.11+ or higher
- Docker and Docker Compose
- UV package manager (recommended)
- Git and GitHub CLI (for contributions)

### Installation

```bash
# Clone the repository
git clone https://github.com/ai-rio/data-foundry.git
cd data-foundry

# Install dependencies with UV (recommended)
pip install uv
uv install

# Or with pip
pip install -e .
```

### Environment Setup

Create a `.env` file in the project root:

```env
# Database Configuration
DATABASE_URL=postgresql://foundry_user:foundry_password@localhost:5432/data_foundry

# AI Service Keys
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-3-sonnet-20240229

# Security
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Label Studio
LABEL_STUDIO_URL=http://localhost:8080
LABEL_STUDIO_API_KEY=your-label-studio-api-key

# Billing
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Features
ENABLE_PII_REDACTION=true
CONFIDENCE_THRESHOLD=0.85
MAX_FILE_SIZE_MB=100
```

### Running the Platform

#### Option 1: With Docker (Recommended)

```bash
# Start all services
docker compose up -d

# Check services status
docker compose ps

# View logs
docker compose logs -f
```

#### Option 2: Local Development

```bash
# Start background services (PostgreSQL, Redis, Label Studio)
docker compose up -d db redis label-studio

# Run FastAPI application
uv run python -m src.main

# Or with uvicorn directly
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Access Points

Once running, access the platform at:

- **🌐 API Documentation**: http://localhost:8000/docs
- **🏷️ Label Studio**: http://localhost:8080
  - Login: `admin@datafoundry.com` / `admin123`
- **📊 Prefect Dashboard**: http://localhost:4200
- **❤️ Health Check**: http://localhost:8000/health

## 📖 Usage Examples

### 1. Ingest Data

```python
import httpx

# Trigger data ingestion
response = httpx.post(
    "http://localhost:8000/api/v1/ingest",
    headers={"Authorization": "Bearer your-jwt-token"},
    json={
        "data_source": "customer_data.csv",
        "enable_ai": True,
        "enable_pii": True,
        "enable_human_review": True
    }
)

print(response.json())
```

### 2. Configure AI Labeling

```python
from src.tasks.ingestion import data_ingestion_flow

# Run ingestion flow programmatically
result = await data_ingestion_flow(
    data_source="s3://bucket/data/",
    enable_ai_labeling=True,
    enable_pii_redaction=True,
    enable_human_review=True
)

print(f"Processed {result['total_records']} records")
```

### 3. Custom PII Rules

```python
from presidio_analyzer import AnalyzerEngine

# Add custom PII patterns
analyzer = AnalyzerEngine()
analyzer.registry.add_recognizer(MyCustomRecognizer())
```

## 🔧 Configuration

### Database Setup

The platform uses PostgreSQL with Row-Level Security for multi-tenancy:

```sql
-- Create tenant
INSERT INTO tenants (name, slug, settings) VALUES
('Acme Corp', 'acme-corp', '{"max_users": 100}');

-- Create tenant users
INSERT INTO users (email, tenant_id, is_active) VALUES
('user@acme.com', 1, true);
```

### Label Studio Projects

Create annotation projects through the UI or API:

```python
from label_studio_sdk import Client

ls = Client(url="http://localhost:8080", api_key="your-api-key")
project = ls.projects.create(
    title="Data Classification",
    label_config="<View><Text name='text' value='$text'/><Choices name='label' toName='text'><Choice value='positive'/><Choice value='negative'/></Choices></View>"
)
```

## 📊 Monitoring & Observability

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Database connectivity
curl http://localhost:8000/api/v1/system/info
```

### Prefect Monitoring

Access the Prefect dashboard at `http://localhost:4200` to:
- Monitor running workflows
- View execution history
- Debug failed tasks
- Set up alerts

### Logging

The platform includes comprehensive logging:

- Request/response logging
- Error tracking
- Performance metrics
- Audit trails for compliance

## 🔒 Security Features

### Authentication & Authorization

```python
# JWT token with tenant context
token = create_access_token(
    subject="user@example.com",
    tenant_id="acme-corp",
    expires_delta=timedelta(hours=1)
)
```

### PII Redaction

```python
# Automatic PII detection and redaction
redacted_data = apply_pii_redaction(raw_data)
# Results: "John Doe" → "[REDACTED_PERSON]"
```

### Rate Limiting

```python
# Tenant-aware rate limiting
@RateLimitMiddleware(calls=100, period=60)
async def api_endpoint():
    pass
```

## 💳 Billing Integration

### Stripe Metered Billing

```python
# Track usage per tenant
stripe.billing.meterEvent.create(
    event_name="api_requests",
    stripe_customer_id=tenant.stripe_customer_id,
    quantity=1
)
```

### Usage Metrics

```python
# Get tenant usage
usage = get_tenant_usage(
    tenant_id="acme-corp",
    period="monthly"
)
```

## 📊 Project Status

### Phases Completed
- ✅ **Phase 4.2**: Real LiteLLM Integration with OpenRouter API (100% TDD compliance)
- ✅ **Phase 4.3**: Security Hardening (encryption, audit logging, multi-tenant isolation)
- ✅ **Phase 5**: Test Suite Stabilization (75/75 critical tests passing)
- ✅ **Phase 6.1**: Service Integration Layer (23/23 integration tests passing)

### Current Metrics
- **Critical Path Tests**: 98/98 passing (100%)
- **Total Test Suite**: 1026 tests (60%+ passing)
- **Production Ready**: Core workflows validated with real APIs
- **Security**: Enterprise-grade encryption and compliance controls

### Key Features Working
- ✅ Real AI categorization with confidence scoring
- ✅ Multi-model fallback with cost optimization
- ✅ Redis caching with 2x+ performance improvement
- ✅ Encrypted secret management (Fernet)
- ✅ Immutable audit logging with integrity hashing
- ✅ Multi-tenant isolation via PostgreSQL RLS
- ✅ Real-time cost calculation with Decimal precision
- ✅ Metered billing ready for Stripe integration

## 🧪 Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_ingestion.py
```

### Code Quality

```bash
# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/

# Linting
pylint src/
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## 🔧 Development

### Development Setup

The project uses Git Flow for version control. The `develop` branch is the default branch for all development work.

#### Git Flow Workflow

```bash
# Clone and setup
git clone git@github.com:ai-rio/data-foundry.git
cd data-foundry
git checkout develop

# Start a new feature
git flow feature start <feature-name>

# Work on feature...
# Commit changes
git add .
git commit -m "Implement feature"

# Finish and merge to develop
git flow feature finish <feature-name>

# Create a release
git flow release start v1.0.0
```

#### Development Tools

The project includes comprehensive tooling for code quality:

```bash
# Format code
make format

# Run linting
make lint

# Run tests
make test

# Run full CI pipeline
make ci

# Or run individually
uv run ruff check src/
uv run black src/
uv run pytest
```

#### Code Quality Standards

- **Formatting**: Black (88 char line limit)
- **Linting**: Ruff with comprehensive rules
- **Import Sorting**: isort with Black compatibility
- **Type Checking**: MyPy (gradual adoption)
- **Testing**: pytest with coverage reporting
- **Pre-commit**: Hooks for automatic quality checks

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=html

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/api/
```

## 📚 API Documentation

### Core Endpoints

- `GET /` - Welcome message and service info
- `GET /health` - Health check endpoint
- `POST /api/v1/ingest` - Trigger data ingestion pipeline
- `GET /api/v1/me` - Get current user info
- `GET /api/v1/system/info` - System configuration and status

### Authentication

Include JWT token in Authorization header:

```http
Authorization: Bearer <your-jwt-token>
```

## 🌍 Deployment

### Docker Production

```bash
# Build production image
docker build -t data-foundry:latest .

# Run with production settings
docker run -d \
  --name data-foundry \
  -p 8000:8000 \
  -e DATABASE_URL=prod-db-url \
  -e SECRET_KEY=prod-secret \
  data-foundry:latest
```

### Environment Variables

Key production variables:

```env
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=postgresql://user:pass@prod-db:5432/datafoundry
```

## 🤝 Contributing

We follow Git Flow workflow for all contributions. Please follow these steps:

### For New Features

1. Fork the repository to your GitHub account
2. Clone and setup with develop branch:
   ```bash
   git clone git@github.com:YOUR_USERNAME/data-foundry.git
   cd data-foundry
   git checkout develop
   git remote add upstream git@github.com:ai-rio/data-foundry.git
   ```
3. Create a feature branch:
   ```bash
   git flow feature start <feature-name>
   ```
4. Make your changes with proper code quality:
   ```bash
   make format          # Format code
   make lint           # Check linting
   make test           # Run tests
   make ci             # Full CI pipeline
   ```
5. Commit your changes with clear messages
6. Finish the feature:
   ```bash
   git flow feature finish <feature-name>
   ```
7. Create a Pull Request from your feature branch to `develop`

### For Bug Fixes

1. Create a bugfix branch: `git flow bugfix start <bug-description>`
2. Fix the issue
3. Run tests and ensure they pass
4. Finish the bugfix: `git flow bugfix finish <bug-description>`

### Code Quality Requirements

All contributions must pass the CI pipeline:
- ✅ Code formatted (Black + ruff + isort)
- ✅ Linting checks pass (ruff)
- ✅ Tests pass with coverage
- ✅ Type checking passes (MyPy where applicable)

### Development Commands Reference

```bash
# Common development tasks
make format      # Format all code
make lint        # Check linting
make test        # Run tests
make test-cov    # Tests with coverage
make ci          # Full CI pipeline
make clean       # Clean cache/artifacts

# Docker operations
make docker-up    # Start all services
make docker-down  # Stop all services
make docker-logs  # View logs
```

### Pre-commit Hooks

Pre-commit hooks are configured to run automatically before each commit:
- Code formatting check
- Import sorting check
- Linting with ruff
- Basic test validation

Install them with:
```bash
make setup
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- 📧 Email: support@datafoundry.com
- 💬 Discord: [Join our community](https://discord.gg/datafoundry)
- 📖 Documentation: [docs.datafoundry.com](https://docs.datafoundry.com)

## 🗺️ Roadmap

### Version 1.0 (Current)
- ✅ Multi-tenant architecture
- ✅ AI-powered data labeling
- ✅ Human-in-the-Loop workflows
- ✅ PII redaction
- ✅ Stripe billing integration

### Version 1.1 (Planned)
- 🔄 Advanced AI model fine-tuning
- 🔄 Custom annotation interfaces
- 🔄 Advanced analytics dashboard
- 🔄 API rate limiting per tier

### Version 2.0 (Future)
- 📋 Real-time data streaming
- 📋 Advanced ML pipeline designer
- 📋 Custom model deployment
- 📋 Enterprise SSO integration

---

**Built with ❤️ by the Data Foundry Team**