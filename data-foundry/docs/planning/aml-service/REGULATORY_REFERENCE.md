# Regulatory Reference Guide: Fintech AML Transaction Labeling Service

**Document Version:** 1.0
**Date:** December 29, 2025
**Purpose:** Complete regulatory framework reference for Data Foundry's managed AML labeling service
**Scope:** United States (FinCEN), European Union (6AMLD/AMLA), Brazil (BCB/COAF)
**Last Updated:** December 29, 2025

---

## Table of Contents

1. [International Standards (FATF)](#1-international-standards-fatf)
2. [United States (FinCEN/OCC)](#2-united-states-fincencocc)
3. [European Union (6AMLD/AMLA)](#3-european-union-6amldamla)
4. [Brazil (BCB/COAF)](#4-brazil-bcbcoaf)
5. [Regulatory Comparison Matrix](#5-regulatory-comparison-matrix)
6. [Service Alignment with Regulations](#6-service-alignment-with-regulations)
7. [Implementation Checklist](#7-implementation-checklist)

---

## 1. International Standards (FATF)

### **FATF Recommendations (2022 Update)**

**Document:** FATF Recommendations - 40 Core Standards
**URL:** https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Fatf-recommendations.html
**Latest Update:** December 2025
**Applicability:** Global baseline - all jurisdictions align to FATF standards

**Key Recommendations for Data Labeling:**
- **R.1:** Identify, assess, understand money laundering risks
- **R.10:** Customer due diligence (CDD) obligations
- **R.13:** Transaction monitoring and reporting
- **R.16:** Travel Rule - information on fund transfers (updated June 2025)
- **R.20:** Reporting of suspicious transactions

**Why This Matters:**
- Your labeling methodology must align with FATF typologies
- All competent regulators (FinCEN, BCB, AMLA) use FATF as reference
- Customers can cite FATF alignment in regulatory defense

---

### **FATF Money Laundering National Risk Assessment Guidance (2024)**

**Document:** Money Laundering National Risk Assessment Guidance
**URL:** https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Money-Laundering-National-Risk-Assessment-Guidance-2024.pdf
**Published:** 2024
**Purpose:** Guides countries on identifying ML risks

**Defines:**
- Risk-based approach methodology
- ML threat assessment framework
- National risk evaluation process
- Transaction typologies and patterns

**For Your Service:**
- Basis for your labeling taxonomy
- Framework for confidence scoring
- Foundation for compliance documentation

---

### **FATF Typologies Reports (Methods & Trends)**

**Document Series:** FATF Typologies Publications
**URL:** https://www.fatf-gafi.org/en/publications/Methodsandtrends/Trade-basedmoneylaunderingtypologies.html
**Includes:**
- Trade-Based Money Laundering (TBML) Typologies
- Virtual Asset Typologies
- Money Laundering Techniques reports
- Emerging ML Methods

**Your Service Uses These For:**
- Structuring/smurfing patterns
- Layering detection
- Mule activity identification
- Sanctions evasion recognition
- PEP (Politically Exposed Person) exposure
- Cross-border fund movement patterns

**Access:** FATF publishes updated typologies annually

---

### **FATF Travel Rule 2025 Revisions (June 2025)**

**Document:** Travel Rule 2025 Revisions - Recommendation 16
**URL:** https://www.mayerbrown.com/en/insights/publications/2025/08/fatf-revises-aml-standards-for-certain-funds-transfers
**Effective:** June 18, 2025
**New Guidance:** Late 2026

**Changes:**
- Expanded funds transfer information requirements
- New beneficiary information obligations
- Enhanced receiving institution responsibilities
- New messaging standards

**Relevant for:** Cross-border transaction labeling, crypto transfers, virtual asset moves

---

## 2. United States (FinCEN/OCC)

### **Primary Legislation: Bank Secrecy Act (BSA)**

**Statute:** 31 USC §5311 et seq.
**Purpose:** Foundation of US AML/CFT compliance
**Enforcement:** FinCEN (Financial Crimes Enforcement Network)

**Core Requirements:**
- Customer identification (CIP - Customer Identification Program)
- Know Your Customer (KYC)
- Customer Due Diligence (CDD)
- Transaction monitoring and reporting
- Suspicious Activity Report (SAR) filing
- Currency Transaction Report (CTR) filing (>$10,000)
- Record keeping (5 years minimum)

**Penalties:**
- Civil: Up to $100,000+ per violation
- Criminal: Up to 10 years imprisonment, $500,000 fines
- Aggregate penalties: Multi-million dollar enforcement actions

---

### **FinCEN Suspicious Activity Report (SAR) FAQs (October 2025)** ⭐ LATEST

**Document:** SAR-FAQs-October-2025.pdf
**URL:** https://www.fincen.gov/system/files/2025-10/SAR-FAQs-October-2025.pdf
**Publication Date:** October 9, 2025
**Status:** Current, just released

**Key Clarifications:**
- SAR requirements and timelines (30 days from detection)
- Structuring vs. normal transactions (>$10k threshold)
- Continuing suspicious activity reporting (90-day intervals optional)
- No documentation required for "no-SAR" decisions
- Risk-based approach expectations

**For Your Service:**
- Defines what qualifies as "suspicious"
- Establishes reporting timelines customers must meet
- Clarifies documentation expectations (your audit trail)
- Shows FinCEN's current enforcement priorities

**Implications:**
- Customers need labeled data within 30-day SAR window
- Your service must deliver labels that support SAR filing
- Documentation you provide becomes customer's regulatory defense

---

### **FinCEN Guidance: SAR Narratives & Supporting Documentation**

**Document 1:** Guidance on Preparing A Complete & Sufficient SAR Narrative
**URL:** https://www.fincen.gov/system/files/shared/sarnarrcompletguidfinal_112003.pdf
**Purpose:** Shows how to document suspicious activity

**Document 2:** SAR Supporting Documentation Guidance (FIN-2007-G003)
**URL:** https://www.fincen.gov/resources/statutes-regulations/guidance/suspicious-activity-report-supporting-documentation
**Purpose:** Explains what documentation regulators expect

**Your Service Provides:**
- Labeled transaction dataset (supports SAR narrative)
- Audit trail documentation (supports FinCEN inquiries)
- Methodology documentation (defends labeling decisions)
- Quality assurance metrics (Cohen's Kappa, inter-annotator agreement)

---

### **FinCEN Frequently Asked Questions Repository**

**URL:** https://www.fincen.gov/resources/frequently-asked-questions-regarding-fincen-suspicious-activity-report-sar
**Content:** Ongoing Q&A addressing SAR filing questions
**Updated:** Regularly (latest October 2025)

**Topics Covered:**
- SAR filing requirements
- Reporting timelines
- Continuing activity rules
- Customer information requirements
- Coordination with law enforcement

---

### **Bank Secrecy Act / AML Manual (FFIEC)**

**Document:** BSA/AML Manual
**URL:** https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/04
**Purpose:** Federal banking guidance on AML compliance

**Covers:**
- Suspicious activity identification
- Transaction monitoring procedures
- SAR preparation and filing
- Quality of SAR narratives
- Risk-based compliance approaches

**For Your Service:**
- Reference for labeling standards
- Framework for quality thresholds
- Guidance on documentation sufficiency

---

### **OCC (Office of the Comptroller of the Currency) Bulletins**

**Latest:** OCC Bulletin 2025-31
**URL:** https://www.occ.treas.gov/news-issuances/bulletins/2025/bulletin-2025-31a.pdf
**Content:** Implements FinCEN SAR guidance for national banks

**Applies To:** All national banks and federal savings banks

---

### **Federal Reserve Guidance**

**Document:** Federal Reserve SR Letters (Supervisory Recommendations)
**Latest:** SR 2504a1 (September 2025)
**URL:** https://www.federalreserve.gov/supervisionreg/srletters/SR2504a1.pdf
**Applies To:** Federal Reserve-supervised institutions

---

### **OFAC (Office of Foreign Assets Control)**

**Sanctions Lists:** https://ofac.treasury.gov/sanctions-lists-and-programs
**Purpose:** Prevent transactions with sanctioned entities

**Your Service Must Address:**
- Cross-reference transactions against OFAC lists
- Flag sanctions evasion patterns
- Document sanctions screening in audit trail

**Recent Enforcement (2025):**
- 8-figure penalties for weak sanctions compliance
- Strict liability (no knowledge/intent required)
- High regulatory focus on sanctions violations

---

## 3. European Union (6AMLD/AMLA)

### **6th Anti-Money Laundering Directive (6AMLD)**

**Official Name:** Directive (EU) 2024/1640
**Adoption:** May 30, 2024
**Force:** July 10, 2024
**Member State Implementation:** By July 10, 2027
**URL:** https://www.europarl.europa.eu/legislative-train/theme-an-economy-that-works-for-people/file-6th-directive-on-amlcft-(amld6)

**Key Changes:**
- Expanded scope (crypto, real estate, luxury goods)
- Stricter customer due diligence (CDD)
- Enhanced beneficial ownership transparency
- Increased penalties (up to €10M or 10% turnover)
- Minimum 4-year imprisonment for ML offenses
- Centralized EU supervisory authority (AMLA)

**Obligations:**
- Risk-based AML/CFT programs
- Transaction monitoring
- Beneficial owner identification
- PEP screening
- Sanctions screening (OFAC lists + EU lists)
- Suspicious activity reporting to FIU

**Penalties:**
- €10 million OR 10% of annual turnover (whichever is greater)
- Periodic penalty payments
- Temporary or permanent business ban
- Individual disqualification

---

### **EU Anti-Money Laundering Authority (AMLA)**

**Regulation:** (EU) 2024/1620
**Established:** Created by new AML package (May 2024)
**Location:** Frankfurt, Germany
**Operational Status:** Becoming fully operational by end of 2025

**AMLA Responsibilities:**
- Direct supervision of high-risk institutions (largest banks, major crypto firms)
- Cross-border operations oversight
- Harmonized enforcement across EU member states
- Emergency coordination in financial crises

**Level 2/3 Mandates Due:** July 2026
- Risk-based approach RTS
- High-risk entity identification
- Suspicious transaction reporting standards (ITS)
- Internal policies guidelines

**Impact on Your Service:**
- EU customers will face AMLA oversight
- Harmonized requirements across member states
- Stricter documentation expectations
- Your labels must support AMLA audits

---

### **EU AML Single Rulebook Implementation**

**Document:** The EU's New AML/CFT Framework
**URL:** https://get.complyadvantage.com/a-guide-to-the-european-unions-new-aml-cft-framework
**Implementation Timeline:**
- July 10, 2025: Transparency register access deadline
- July 10, 2026: Level 2/3 secondary legislation due
- July 10, 2027: Full member state compliance deadline

**What Single Rulebook Contains:**
- Harmonized CDD procedures
- Unified transaction monitoring standards
- Standardized risk assessment frameworks
- Common beneficial owner identification methods
- EU-wide sanctions list integration

---

### **EU 6AMLD Implementation Guides**

**Document 1:** The 6th AML Directive in Germany (Stripe)
**URL:** https://stripe.com/resources/more/sixth-eu-money-laundering-directive-germany
**Content:** Practical implementation guide

**Document 2:** Understanding EU's 6th AML Directive (Ondato)
**URL:** https://ondato.com/blog/6th-anti-money-laundering-directive/
**Content:** Overview of directive requirements

**Document 3:** Dilisense 6AMLD Overview
**URL:** https://dilisense.com/en/insights/understanding-the-sixth-anti-money-laundering-directive
**Content:** Business impact analysis

---

### **EU Council & Parliament Resources**

**Official:** European Parliament Legislative Train
**URL:** https://www.europarl.europa.eu/RegData/etudes/IDAN/2025/773721/ECTI_IDA(2025)773721_EN.pdf
**Content:** AMLA work programme and timeline

---

## 4. Brazil (BCB/COAF)

### **Core Legislation: Law No. 9,613/1998 (Anti-Money Laundering Law)**

**Official Name:** Lei nº 9.613, de 3 de março de 1998
**Purpose:** Criminalizes money laundering and asset concealment
**Created:** COAF (Conselho de Controle de Atividades Financeiras)
**URL:** https://www.b3.com.br/data/files/EA/D3/6D/1F/BE86B51095EE46B5790D8AA8/Law9613.pdf

**Core Obligations:**
- Customer identification (KYC)
- Transaction record keeping (5 years minimum)
- Suspicious activity monitoring and reporting
- Risk-based AML procedures
- Internal controls and compliance programs

**Penalties:**
- Fines up to 2x transaction amount
- Up to R$200,000 fines
- 10-year management disqualification
- Cancellation of operating authorization (permanent closure)

**Criminal Penalties:**
- Up to 10 years imprisonment
- Asset forfeiture

---

### **Law No. 12,683/2012 (2012 Amendments)**

**Strengthened:**
- Law 9,613 enforcement
- COAF powers
- Penalties
- Reporting requirements

**Current Status:** Still in force (foundational law)

---

### **Law No. 13,260/2016 (Counter-Terrorism Financing)**

**Purpose:** Complements AML law with CTF provisions
**Applies:** Together with Law 9,613

---

### **COAF (Conselho de Controle de Atividades Financeiras)**

**What is COAF:**
- Brazil's Financial Intelligence Unit (FIU)
- Operates under Central Bank of Brazil (since 2020)
- Acts independently but administratively linked to BCB
- Equivalent to FinCEN in United States

**URL:** https://www.coaf.gov.br (Portuguese)
**English Contact:** https://complyadvantage.com/insights/coaf/

**COAF Responsibilities:**
- Receives and analyzes suspicious transaction reports
- Investigates money laundering activities
- Issues AML/CFT guidelines
- Applies administrative penalties
- Represents Brazil in international AML forums (FATF)

**Reporting Requirements:**
- **Suspicious activities: Within 24 hours** ⚡ (STRICT - fastest in world)
- Cash transactions >R$50,000: Report to COAF
- Fintechs now use same reporting system as banks (August 2025)

---

### **COAF Resolution No. 36/2021 (New AML/CFT Requirements)**

**Publication Date:** March 10, 2021
**Effective Date:** June 1, 2021
**Purpose:** Establishes new requirements and internal controls

**Key Changes:**
- Risk-based AML approach (aligns with FATF)
- Enhanced CDD procedures
- Transaction monitoring standards
- Suspicious activity detection criteria
- Internal control requirements

**Alignment:**
- Aligns with CVM Instruction No. 617/2019 (securities)
- Aligns with BCB Circular No. 3,978/2020 (banking)
- Aligns with SUSEP Circular No. 612/2020 (insurance)

**For Your Service:**
- Defines what "suspicious" means in Brazil
- Establishes documentation standards
- Framework for labeling methodology

---

### **COAF Typologies & Cases Publications**

**Publication:** "Casos e Casos" (Cases and Cases)
**URL:** https://www.lickslegal.com/post/typologies-of-money-laundering-and-terrorist-financing-by-coaf
**Purpose:** Disseminate ML/TF patterns and awareness

**Defines:**
- Money laundering typologies
- Terrorist financing typologies
- Emerging ML methods
- Real-world case examples
- Red flag indicators

**Your Service Uses For:**
- Transaction pattern recognition
- Risk factor identification
- Labeling taxonomy alignment
- Educational materials for annotators

---

### **BCB (Banco Central do Brasil) Regulations**

### **BCB Circular No. 3,978/2020 (Risk-Based AML Approach)** ⭐ FOUNDATIONAL

**Publication:** October 1, 2020
**Purpose:** Establishes risk-based approach to ML/TF prevention
**Applies To:** All financial institutions and payment providers

**Requirements:**
- Identify and assess ML/TF risks
- Understand customer risk profile
- Implement controls proportionate to risk
- Document risk assessments
- Maintain policies and procedures
- Employee training
- Independent audits

**Key Principle:** "Risk-Based Approach"
- Not one-size-fits-all
- Tailored to institution and customer risk
- Documented and defensible

**For Your Service:**
- Framework for confidence scoring
- Basis for risk factor identification
- Methodology for labeling standards

---

### **BCB Resolution No. 494/2025 (September 5, 2025)**

**Purpose:** Payment Institution Authorization Requirements
**Key Change:** All payment institutions (including fintechs) must obtain prior authorization

**Impact:**
- No more exemptions for small-volume providers
- Stricter compliance requirements
- Enhanced AML/CFT obligations

---

### **BCB Resolutions 496-497/2025 (September 5, 2025)**

**Purpose:** Transaction Limits for Unauthorized Institutions
**Limits:** R$15,000 per Pix/TED transaction

**Impact:**
- Forces fintechs to get authorization or lose business
- Increases compliance pressure
- Creates demand for AML labeling services

---

### **BCB Resolution No. 520/2025 (November 10, 2025)** ⭐ NEW - VASPS/CRYPTO

**Purpose:** Virtual Asset Service Providers (VASPs) Framework
**Effective:** November 10, 2025

**Covers:**
- VASP governance requirements
- Capital and risk management standards
- AML/CTF obligations for crypto transactions
- Travel Rule requirements
- Client asset segregation
- Cybersecurity standards
- Transition provisions

**Impact on Your Service:**
- New market demand (crypto labeling)
- Transaction monitoring for virtual assets
- OFAC screening for crypto transfers
- Travel Rule compliance support

---

### **BCB Circular Letter 3,977 & BCB Circular Letter 4,001**

**Purpose:** Implement AML/CFT procedures for financial institutions
**Content:** Procedural guidance for compliance

---

### **BCB Resolution No. 538/2025 (December 18, 2025)**

**Purpose:** Enhanced Cybersecurity Requirements
**Compliance Deadline:** March 1, 2026

**Applies To:** Cloud services, data processing, computing resources
**Impact:** Affects data storage and processing for labeling service

---

### **Brazilian Data Protection Law (LGPD)**

**Official Name:** Lei Geral de Proteção de Dados (Law 13,709/2018)
**Compliance:** Mandatory for all data processing in Brazil

**Key Requirements:**
- Only collect essential data
- Disclose data usage clearly
- Respect 5-year retention limits
- Delete unnecessary data
- Obtain consent where required

**Your Service Must Address:**
- Customer transaction data privacy
- Data minimization principles
- Secure data handling
- Compliance documentation

---

### **Brazil's National Risk Assessment (NRA)**

**Document:** National Risk Assessment - Executive Summary
**URL:** https://www.gov.br/coaf/pt-br/centrais-de-conteudo/publicacoes/avaliacao-nacional-de-riscos/4-1_executive-summary_national-risk-assessment_ing.pdf
**Purpose:** Government-wide ML/TF risk evaluation

**Content:**
- ML/TF threat assessment
- Vulnerability identification
- Risk mitigation strategies
- Sector-specific risks
- Geographic vulnerabilities

---

### **Brazil Federal Revenue Reporting Requirements**

**Regulation:** Normative Instruction No. 2,278/2025 (August 29, 2025)
**Purpose:** Financial reporting via e-Financeira system

**Applies To:** All fintechs and digital payment companies
**Requirements:**
- Report customer financial data
- Account balances and transactions
- Cross-check against income tax filings
- Secure digital reporting

**Impact:** Fintechs now have BANK-LEVEL reporting obligations

---

### **Brazil FinTech Guides**

**Comprehensive Guide:** Brazil FinTech Comparative Guide
**URL:** https://www.mondaq.com/guides/results/10/130/all/brazil-fintech
**Content:** Fintech-specific compliance requirements

**KYC Guide:** KYC/KYB Requirements for Fintech
**URL:** https://withpersona.com/blog/understanding-kyc-and-kyb-requirements-in-brazil-for-fintech/

**Regulation Summary:** 2025 Fintech Regulation Guide - Brazil
**URL:** https://practiceguides.chambers.com/practice-guides/financial-services-regulation-2025/brazil/trends-and-developments

---

## 5. Regulatory Comparison Matrix

| Aspect | United States (FinCEN) | European Union (6AMLD/AMLA) | Brazil (BCB/COAF) |
|--------|----------------------|---------------------------|------------------|
| **Primary Law** | Bank Secrecy Act (31 USC §5311) | Directive 2024/1640 | Law 9,613/1998 |
| **Amendment Law** | n/a | n/a | Law 12,683/2012 |
| **Regulator** | FinCEN | AMLA (new 2025) | COAF + BCB |
| **Reporting Timeline** | 30 days | 24 hours | **24 hours ⚡** |
| **FIU** | FinCEN | AMLA (Frankfurt) | COAF |
| **Risk-Based Approach** | Yes (FinCEN guidance) | Yes (6AMLD) | Yes (Circular 3,978) |
| **FATF Aligned** | Yes | Yes | Yes |
| **Record Retention** | 5 years | 5 years | 5 years |
| **SAR/STR Filing** | 30-day deadline | 24-hour deadline | 24-hour deadline |
| **Crypto Regulated** | Partial (evolving) | MiCA (separate) | Yes (Nov 2025 - Resolution 520) |
| **CTF (Counter-Terrorism)** | Included (USA PATRIOT) | Included (6AMLD) | Included (Law 13,260/2016) |
| **Travel Rule Implemented** | Via FATF R.16 | Via AML Regulation | Via BCB (VASP rules) |
| **Penalties - Civil** | $100k+ per violation | €10M or 10% turnover | 2x amount + R$200k |
| **Penalties - Criminal** | 10 years + $500k | 4+ years imprisonment | 10 years imprisonment |
| **Independent Audit** | Required | Required | Required |
| **CDD Standards** | Risk-based | Risk-based (enhanced 6AMLD) | Risk-based (Circular 3,978) |
| **Latest Updates** | Oct 2025 (SAR FAQs) | July 2024 (force) | Dec 2025 (cybersecurity) |

---

## 6. Service Alignment with Regulations

### **How Data Foundry AML Labeling Service Aligns**

Your service aligns with all three jurisdictions by:

#### **1. Labeling Taxonomy Alignment**
```
Your Labeling Framework:
├── FATF Typologies (international standard)
│   ├── Structuring/Smurfing
│   ├── Layering
│   ├── Mule Activity
│   ├── Trade-Based ML
│   ├── Sanctions Evasion
│   └── PEP Exposure
├── FinCEN SAR Criteria (US compliance)
│   ├── Unusual transaction patterns
│   ├── Customer behavior anomalies
│   ├── Threshold-breaking structures
│   └── Cross-border red flags
├── COAF Typologies (Brazil alignment)
│   ├── Casos e Casos patterns
│   ├── Risk-based assessment
│   └── Local ML trends
└── AMLA Standards (EU alignment)
    ├── High-risk entity identification
    ├── Beneficial owner concerns
    └── Harmonized red flags
```

#### **2. Compliance Documentation**
Your service delivers:
- **Labeled dataset** - Supports customer SAR filing
- **Audit trail** - Shows regulatory defensibility
- **Methodology documentation** - Aligns with FATF + FinCEN + COAF + AMLA standards
- **Quality metrics** - Cohen's Kappa ≥0.80 (inter-annotator agreement)
- **Confidence scores** - Support risk-based approach
- **Investigation notes** - Enable SAR narrative writing

#### **3. Regulatory Timeline Alignment**

| Jurisdiction | Timeline | Your Service Role |
|---|---|---|
| **US (FinCEN)** | 30 days to SAR filing | Label data within 30 days |
| **EU (AMLA)** | 24 hours to reporting | Label data within 24 hours |
| **Brazil (COAF)** | **24 hours to COAF** | Label data within 24 hours (fastest market!) |

#### **4. Risk-Based Approach**
- Your confidence scoring supports risk-based categorization
- Your methodology follows FATF R.1 (identify and assess risks)
- Your labels enable proportionate compliance responses

---

## 7. Implementation Checklist

### **Phase 1: Regulatory Alignment (Week 1-2)**

**Documentation:**
- [ ] Obtain FATF Recommendations 2022 PDF (complete reference)
- [ ] Download FinCEN SAR FAQs October 2025
- [ ] Download BCB Circular 3,978/2020 (Portuguese)
- [ ] Download COAF Resolution 36/2021 (Portuguese)
- [ ] Download 6AMLD Directive 2024/1640
- [ ] Compile COAF Typologies & Casos e Casos guide

**Reference Library:**
- [ ] Create regulatory_reference folder
- [ ] Organize by jurisdiction (US/, EU/, BR/)
- [ ] Index documents by effective date
- [ ] Version control all documents

**Service Documentation:**
- [ ] Create "Regulatory Alignment" section in service spec
- [ ] Document how labels align with FATF typologies
- [ ] Document how methodology satisfies FinCEN expectations
- [ ] Document how audit trail meets COAF 24-hour timeline
- [ ] Document AMLA alignment for EU customers

---

### **Phase 2: Labeling Methodology (Week 2-3)**

**Taxonomy Development:**
- [ ] Map FATF typologies to specific labels
- [ ] Define confidence thresholds per jurisdiction
- [ ] Create risk factor taxonomy
- [ ] Establish investigation notes guidelines

**Quality Standards:**
- [ ] Define Cohen's Kappa target (≥0.80)
- [ ] Establish inter-annotator agreement process
- [ ] Create consistency audit procedures
- [ ] Define sample re-labeling rate (10%)

**Audit Trail:**
- [ ] Document labeling methodology version
- [ ] Record annotator IDs
- [ ] Timestamp all labels
- [ ] Create SHA256 hash for audit verification

---

### **Phase 3: Customer-Facing Alignment (Week 3)**

**Service Specification:**
- [ ] List all regulatory references
- [ ] Explain FATF alignment explicitly
- [ ] Show how labels support SAR filing
- [ ] Demonstrate timeline compliance (30d US, 24h EU/BR)
- [ ] Include regulatory disclosure language

**Customer Communications:**
- [ ] Create "Regulatory Defensibility" section
- [ ] Explain audit trail documentation
- [ ] Show quality metrics (IAA scores)
- [ ] Provide compliance report samples

**Legal/Compliance:**
- [ ] Consult with compliance counsel
- [ ] Review liability terms
- [ ] Ensure data handling complies with LGPD/GDPR
- [ ] Document security measures

---

### **Phase 4: Go-To-Market (Week 4)**

**Pitch Materials:**
- [ ] Create "Regulatory Compliance" one-pager
- [ ] List all reference documents in appendix
- [ ] Show regulatory timeline alignment
- [ ] Include compliance cost/risk analysis

**Customer Onboarding:**
- [ ] Provide regulatory reference guide to customers
- [ ] Explain audit trail importance
- [ ] Show example compliance reports
- [ ] Set expectations for timeline

---

## Regulatory Timeline Summary

### **Recent Changes (2025)**

| Date | Jurisdiction | Change | Impact |
|------|---|---|---|
| **Oct 9, 2025** | US | FinCEN SAR FAQs updated | Clarified SAR requirements |
| **Aug 29, 2025** | Brazil | Federal Revenue NI 2,278 | Fintechs now report like banks |
| **Sept 5, 2025** | Brazil | BCB Resolutions 494-498 | All fintechs need authorization |
| **Nov 10, 2025** | Brazil | BCB Resolutions 519-521 | VASP crypto framework |
| **Dec 18, 2025** | Brazil | BCB Resolution 538 | Cybersecurity requirements |
| **June 2025** | International | FATF Travel Rule revisions | Updated funds transfer rules |

### **Upcoming Deadlines**

| Date | Jurisdiction | Requirement |
|------|---|---|
| **March 1, 2026** | Brazil | BCB 538 cybersecurity compliance |
| **July 2026** | EU | AMLA Level 2/3 mandates due |
| **July 10, 2027** | EU | Member state full 6AMLD compliance |

---

## Quick Reference: Where to Find Each Regulation

### **FATF (International)**
- **Website:** https://www.fatf-gafi.org
- **Recommendations:** https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Fatf-recommendations.html
- **Typologies:** https://www.fatf-gafi.org/en/publications/Methodsandtrends/

### **FinCEN (US)**
- **Website:** https://www.fincen.gov
- **SAR FAQs:** https://www.fincen.gov/system/files/2025-10/SAR-FAQs-October-2025.pdf
- **SAR Guidance:** https://www.fincen.gov/resources/statutes-regulations/guidance/
- **Sanctions Lists:** https://ofac.treasury.gov/sanctions-lists-and-programs

### **AMLA (EU)**
- **Website:** https://www.amla.europa.eu (launching 2025)
- **6AMLD Text:** https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024L1640
- **AMLA Regulation:** https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1620

### **BCB (Brazil)**
- **Website:** https://www.bcb.gov.br/en
- **Regulations Search:** https://www.bcb.gov.br/en/financialstability/regulation
- **AML Info:** https://www.bcb.gov.br/en/financialstability/moneylaundering

### **COAF (Brazil)**
- **Website:** https://www.coaf.gov.br (Portuguese)
- **Typologies/Cases:** Published quarterly
- **Contact:** COAF - Brasília, DF

---

## Document Metadata

**Prepared By:** Data Foundry Strategic Planning
**Version:** 1.0
**Effective Date:** December 29, 2025
**Review Schedule:** Quarterly (regulatory updates)
**Next Review:** March 31, 2026

**Key Review Dates:**
- March 1, 2026 - BCB 538 cybersecurity deadline
- July 2026 - AMLA Level 2/3 mandates released
- 2026 Q4 - FATF travel rule guidance published

---

## Document Usage

**Intended For:**
- Data Foundry service specification
- Customer-facing regulatory documentation
- Compliance team reference
- Sales/marketing materials
- Regulatory defensibility arguments

**Distribution:**
- Include full document in service spec appendix
- Reference in customer contracts
- Provide to customer legal teams
- Use in regulatory conversations

**Confidentiality:** Non-confidential (based on public regulatory documents)

---

**END OF DOCUMENT**

---

## Appendix A: Regulatory Document URLs (Complete Index)

### **FATF Documents**
1. FATF Recommendations 2022: https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Fatf-recommendations.html
2. ML National Risk Assessment 2024: https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Money-Laundering-National-Risk-Assessment-Guidance-2024.pdf
3. Trade-Based ML Typologies: https://www.fatf-gafi.org/en/publications/Methodsandtrends/Trade-basedmoneylaunderingtypologies.html
4. Travel Rule 2025 Revisions: https://www.mayerbrown.com/en/insights/publications/2025/08/fatf-revises-aml-standards-for-certain-funds-transfers

### **FinCEN Documents (US)**
5. FinCEN SAR FAQs October 2025: https://www.fincen.gov/system/files/2025-10/SAR-FAQs-October-2025.pdf
6. SAR Narrative Guidance: https://www.fincen.gov/system/files/shared/sarnarrcompletguidfinal_112003.pdf
7. SAR Supporting Documentation: https://www.fincen.gov/resources/statutes-regulations/guidance/suspicious-activity-report-supporting-documentation
8. BSA/AML Manual: https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/04
9. OCC Bulletin 2025-31: https://www.occ.treas.gov/news-issuances/bulletins/2025/bulletin-2025-31a.pdf

### **AMLA/6AMLD Documents (EU)**
10. 6AMLD Directive 2024/1640: https://www.europarl.europa.eu/legislative-train/theme-an-economy-that-works-for-people/file-6th-directive-on-amlcft-(amld6)
11. AMLA Work Programme: https://www.europarl.europa.eu/RegData/etudes/IDAN/2025/773721/ECTI_IDA(2025)773721_EN.pdf
12. EU AML Framework Guide: https://get.complyadvantage.com/a-guide-to-the-european-unions-new-aml-cft-framework
13. 6AMLD Implementation (Stripe): https://stripe.com/resources/more/sixth-eu-money-laundering-directive-germany

### **BCB/COAF Documents (Brazil)**
14. Law 9,613/1998 Full Text: https://www.b3.com.br/data/files/EA/D3/6D/1F/BE86B51095EE46B5790D8AA8/Law9613.pdf
15. BCB Circular 3,978/2020: https://www.bcb.gov.br/en/financialstability/regulation
16. COAF Resolution 36/2021: https://www.lickslegal.com/post/typologies-of-money-laundering-and-terrorist-financing-by-coaf
17. National Risk Assessment: https://www.gov.br/coaf/pt-br/centrais-de-conteudo/publicacoes/avaliacao-nacional-de-riscos/
18. BCB Resolution 520/2025 (VASP): https://notabene.id/post/brazils-central-bank-regulates-virtual-asset-service-providers-what-bcb-resolutions-mean-for-crypto-compliance
19. Federal Revenue NI 2,278/2025: https://www.trade.gov/market-intelligence/brazil-fintechs-required-share-financial-data

---

**Total Regulatory Documents Referenced:** 19 primary sources
**Jurisdictions Covered:** 3 (US, EU, Brazil)
**Document Completeness:** Comprehensive
**Last Verified:** December 29, 2025
