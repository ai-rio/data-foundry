This **Project Brief** is the definitive technical and strategic manual for **Data Foundry**. It consolidates every architectural decision, library, and repository we have discussed into a production-ready blueprint.

---

# 📑 Project Brief: Data Foundry (EaaS)

**Version:** 1.0 (2025 Edition)

**Objective:** To build a high-margin **Enrichment-as-a-Service** platform that automates data cleaning and labeling for high-stakes industries (Healthcare, Finance, E-commerce) using a hybrid AI + Human-in-the-Loop (HITL) model.

---

## 1. Technical Architecture & Logic

The platform operates as a multi-stage "refinery." Raw data enters via a tenant-scoped API, is scrubbed for privacy, labeled by AI, and—if confidence is low—routed to human experts for final verification.

### **Core Workflows:**

* **Multi-Tenancy:** Enforced at the database level via **PostgreSQL Row-Level Security (RLS)**.
* **PII/PHI Redaction:** Integrated at the ingestion gate using **Microsoft Presidio**.
* **Confidence Routing:** AI generates a score ( to ). Scores  are flagged for human review.
* **Metered Billing:** Usage is tracked in real-time and synced to **Stripe Meters** (`AI_LABELS` vs. `HUMAN_AUDITS`).

---

## 2. Software Bill of Materials (Dependencies)

Add these to your `requirements.txt` or `pyproject.toml`.

| Category | Package | Purpose |
| --- | --- | --- |
| **API Framework** | `fastapi[all]` | High-performance async API layer. |
| **Data Models** | `sqlmodel` | Pydantic + SQLAlchemy for tenant-safe data. |
| **ELT Engine** | `dlt` | Automated schema evolution and data loading. |
| **AI Labeling** | `refuel-autolabel` | ML labeling engine with confidence calibration. |
| **Privacy** | `presidio-analyzer`, `presidio-anonymizer` | PII/PHI detection and redaction. |
| **Orchestration** | `prefect` | Workflow management for ingestion and labeling. |
| **Background Tasks** | `celery`, `redis` | Asynchronous processing of large datasets. |
| **HITL UI** | `label-studio-sdk` | Integration with the human review interface. |
| **Business/Billing** | `stripe` | 2025 Metered Billing API integration. |
| **Database Driver** | `psycopg2-binary` | Primary driver for PostgreSQL. |

---

## 3. GitHub Repository Catalog

These are your primary sources for boilerplate, inspiration, and core logic.

* **Project Shell:** [tiangolo/full-stack-fastapi-template](https://github.com/tiangolo/full-stack-fastapi-template) (The industry-standard SaaS boilerplate).
* **ORM Layer:** [fastapi/sqlmodel](https://github.com/fastapi/sqlmodel) (Essential for your shared-schema architecture).
* **Ingestion:** [dlt-hub/dlt](https://github.com/dlt-hub/dlt) (The "Data Load Tool" to handle messy client files).
* **Privacy Engine:** [microsoft/presidio](https://github.com/microsoft/presidio) (To ensure HIPAA/GDPR compliance).
* **ML Engine:** [refuel-ai/autolabel](https://github.com/refuel-ai/autolabel) (The core "brain" for your labeling tasks).
* **Human UI:** [HumanSignal/label-studio](https://github.com/HumanSignal/label-studio) (The interface for your human reviewers).

---

## 4. Execution Roadmap (5-Week MVP)

| Week | Phase | Key Milestone |
| --- | --- | --- |
| **1** | **Foundations** | Setup FastAPI + SQLModel + PostgreSQL RLS for tenant isolation. |
| **2** | **Ingestion** | Deploy `dlt` pipelines with a `Presidio` redaction middleware. |
| **3** | **Enrichment** | Connect `Autolabel` (GPT-4o/Claude) and generate confidence scores. |
| **4** | **Human-in-Loop** | Integrate `Label Studio` for review and `Stripe` for metered billing. |
| **5** | **Hardening** | Deploy to **Railway** or **AWS**; run multi-tenant "Intrusion Tests." |

---

## 5. Standards & Compliance (2025)

* **Data Provenance:** Every record is stored with a `provenance_metadata` JSONB blob (e.g., `{"model": "gpt-4o", "temp": 0.3, "prompt_hash": "a1b2..."}`).
* **Zero-Plaintext Policy:** No raw sensitive data (SSNs, medical IDs) is stored in the database without redaction.
* **Billing Transparency:** Metered usage is updated daily, allowing customers to see their "AI savings" vs. "Human costs."

---

## 🚀 The "Start Now" Command

To initialize your local development environment and verify your stack, run:

```bash
# Initialize project directory
mkdir data_foundry && cd data_foundry

# Install all core dependencies
pip install fastapi[all] sqlmodel dlt prefect celery redis refuel-autolabel label-studio-sdk presidio-analyzer presidio-anonymizer stripe psycopg2-binary

# Verify Python environment
python -c "import fastapi, dlt, sqlmodel; print('Data Foundry Stack: READY')"

```

