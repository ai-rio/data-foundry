# Data Foundry (EaaS)

**Enrichment-as-a-Service platform** - AI-powered data cleaning and labeling with Human-in-the-Loop verification for Healthcare, Finance, and E-commerce.

## Architecture

A multi-stage data refinery that:
1. Ingests raw data through tenant-scoped APIs
2. Redacts PII/PHI using Microsoft Presidio
3. Labels data using AI (GPT-4o/Claude) with confidence scoring
4. Routes low-confidence predictions to human experts
5. Tracks usage for metered billing

## Tech Stack

- **API**: FastAPI with async support
- **Database**: PostgreSQL with Row-Level Security (RLS)
- **Data Processing**: SQLModel, DLT for ELT
- **AI/ML**: refuel-autolabel for automated labeling
- **Privacy**: Microsoft Presidio for PII/PHI redaction
- **Orchestration**: Prefect for workflows
- **Background Tasks**: Celery + Redis
- **HITL UI**: Label Studio integration
- **Billing**: Stripe metered billing

## Quick Start

```bash
# Install dependencies
uv install

# Activate virtual environment
source .venv/bin/activate

# Verify installation
python -c "import fastapi, dlt, sqlmodel; print('Data Foundry Stack: READY')"
```

## Project Status

- [x] Project initialization
- [ ] Week 1: Foundation setup (FastAPI + SQLModel + PostgreSQL RLS)
- [ ] Week 2: Ingestion pipeline (DLT + Presidio)
- [ ] Week 3: AI enrichment (Autolabel + confidence scoring)
- [ ] Week 4: Human-in-the-Loop (Label Studio + Stripe billing)
- [ ] Week 5: Deployment and hardening

## Repository

https://github.com/ai-rio/data-foundry