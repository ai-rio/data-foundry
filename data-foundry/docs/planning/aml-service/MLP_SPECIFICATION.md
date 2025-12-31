# Minimum Lovable Product (MLP) Specification: Data Foundry AML Service

**Document Status:** Strategic Blueprint for Fintech AML Labeling Service
**Date:** December 29, 2025
**Context:** Shifting from generic "Managed Data Outcomes" to expertise-driven fintech compliance service

---

## Executive Summary

Data Foundry's AML Service MLP is **NOT** a feature-rich platform. It's a **regulatory expertise service** delivered through thoughtful UX, focused on making compliance feel effortless and trustworthy.

**The Lovable Core:**
- Fintech companies send suspicious transaction data
- Our regulatory experts label it with perfect accuracy + explain reasoning
- They receive audit-ready labels + compliance documentation
- They feel confident their AML program is defensible

**Not a commodity platform. A trusted expert in accessible form.**

---

## Part 1: Why MLP (Not MVP) for AML

### The MVP Trap in Compliance Services

**MVP Approach** (What NOT to do):
- Build a feature-rich labeling platform (5+ AML rule types, configurable workflows)
- Launch with "basic" regulatory coverage (covers FinCEN SAR requirements)
- Move fast, iterate on features
- **Problem**: Compliance teams don't want more features—they want *reliability and trust*
- **Risk**: Compete on features with Scale AI, Labelbox, etc. (lose on budget and brand)

### The MLP Advantage in Compliance Services

**MLP Approach** (What we're doing):
- Deep expertise in ONE regulatory scenario (high-risk cross-border transfers)
- Perfect accuracy (98%+) with explicit reasoning for every decision
- Simple, beautiful interface that demonstrates expertise
- Build trust through transparency and consistency
- **Competitive advantage**: Fintech compliance officers will advocate for a service they trust
- **Risk mitigation**: Focus on what you can own (expertise), not what you can't (features)

**Why this works for your team:**
- You don't have 100+ employees to scale platform features
- Your advantage IS regulatory knowledge (deep research into FinCEN, COAF, AMLA)
- Fintech compliance is about trust, not features
- One delighted customer in fintech leads to 5+ referrals (tight community)

---

## Part 2: The Lovable Core – What You're Actually Selling

### Not Features, But Outcomes You Own

| What Competitors Say | What We Say |
|---------------------|-----------|
| "70+ rule types" | "Every suspicious transaction gets expert review" |
| "Configure your labeling schema" | "We've mapped the labeling schema to regulatory standards" |
| "95% auto-labeling" | "100% accurate labels you can defend to auditors" |
| "Get results in 24 hours" | "Get results with regulatory confidence" |
| "Compliance dashboard" | "Compliance dashboard that explains *why* we flagged that transaction" |

### The Specific Expertise You're Selling

**For Fintech Companies Moving from Rules-Based to ML-Based AML:**

**Current Problem:**
- Rules-based systems (IF amount > $10k AND country = high-risk THEN flag) have 40-60% false positive rates
- They want to train ML models on labeled transaction data
- But: No one provides *audit-ready* labeled training data
- They spend 2-4 months manually labeling transactions (expensive, slow, inconsistent)

**Your Solution:**
- Provide labeled transaction datasets trained on FATF-aligned methodology
- Every label includes:
  - AML suspicion level (1-5 risk scale aligned to FATF typologies)
  - Specific FATF typology match (structuring, layering, mule activity, etc.)
  - Regulatory standard met (FinCEN SARable, COAF-reportable, AMLA-compliant)
  - Explicit reasoning (what triggered the flag, which regulation applies)
  - Confidence score (our team's agreement on the label)
- Result: They can train ML models AND defend the training methodology to regulators

**Why This Is Lovable:**
- Fintech founder: "They understand AML better than I do"
- Compliance officer: "These labels I can actually defend"
- Regulator (if audited): "They followed FATF standards and documented it"

---

## Part 3: The Lovable Product – Minimal Scope, Maximum Polish

### What This MLP Covers (Scope: Intentionally Small)

**Primary Use Case: Transaction Screening for High-Risk Corridors**

**Supported Scenarios (v1):**
1. **Cross-border transfers** (USD/EUR/BRL to emerging markets)
   - Flag structuring patterns (multiple small transfers → single large amount)
   - Flag high-risk jurisdictions + beneficial ownership gaps
   - Flag mule activity (unusual velocity, patterns)

2. **Sanctions evasion screening** (PEP exposure, geographic triggers)
   - FATF R.6 compliance: PEP exposure detection
   - FATF R.7: Beneficial ownership screening
   - Geographic risk (sends to OFAC-sanctioned entities)

3. **Trade-based money laundering red flags** (for fintechs handling international trade)
   - Invoice manipulation (over/under-invoicing)
   - Circular flows (A→B→A with value extraction)
   - Concealment indicators

**NOT Covered in v1:**
- ❌ Domestic transaction screening (different regulatory framework)
- ❌ Customer due diligence (KYC labeling) - separate product
- ❌ Ongoing transaction monitoring rules - separate service
- ❌ Sanctions list screening (use existing OFAC tools; we add interpretation)

**Why Small Scope = Lovable:**
- You own these 3 scenarios deeply
- Compliance teams know exactly what they're getting
- Better to be the best-in-class for high-risk corridors than mediocre at everything
- Foundation for expansion once you prove expertise

### The User Experience (How Expertise Shows)

#### Primary User Journey: "The Audit-Ready Dataset in 24 Hours"

**Day 1: Customer (Fintech Compliance Manager)**
1. **7 PM:** Logs into Data Foundry
2. **7:02 PM:** Drags CSV file → "Banking Transaction Data for ML Training"
   - 10,000 recent cross-border transfers
   - Columns: sender_id, recipient_country, amount, timestamp
3. **7:05 PM:** Selects scenario: "Cross-border transfers (high-risk corridors)"
4. **7:06 PM:** Sees estimate: "$120 (10,000 × $0.012/transaction)"
5. **7:07 PM:** Clicks "Submit for Expert Review"
6. **System response:** "Your data is being reviewed by our regulatory experts. You'll receive audit-ready labels by 8 AM tomorrow. Check back anytime for progress."

**Day 2: 8 AM (The Lovable Moment)**
1. **Email notification:** "Your AML transaction labels are ready"
2. **Downloads CSV with columns:**
   - `transaction_id` (original)
   - `aml_risk_level` (1-5, FATF-aligned)
   - `aml_typology` (structuring, mule activity, trade-based ML, etc.)
   - `regulatory_flag` (FinCEN SARable, COAF-reportable, AMLA-relevant)
   - `expert_reasoning` ("High-risk pattern: 8 transfers <$10k from same sender to high-risk jurisdiction within 2 hours, then consolidated by single recipient")
   - `confidence_score` (0.95 = 95% inter-annotator agreement)
   - `regulatory_standard` ("FATF R.6 (PEP), FATF R.7 (Beneficial Ownership)")

3. **Also receives:**
   - **Audit Report** (1-page summary):
     - "10,000 transactions reviewed using FATF-aligned methodology"
     - "1,340 flagged as suspicious (13.4% flag rate)"
     - "High confidence labels for training ML models"
     - "All labels defensible under FinCEN guidelines (reference: [SAR FAQ link])"
     - "Methodology: [Link to Data Foundry Regulatory Reference]"
   - **Confidence Dashboard** (interactive):
     - Distribution of risk levels
     - Top flagged typologies
     - Geographic patterns
     - Explains what each typology means in regulatory context

4. **Compliance Manager's Reaction:**
   - "I can actually understand why these are flagged"
   - "I can use this to train our ML model with confidence"
   - "If a regulator asks, I can explain our labeling methodology"
   - **LOVES IT.** Tells their CTO, "You need to see this"

#### Secondary Journey: "Edge Case Consultation" (Adds Love)

**For complex/ambiguous transactions:**
1. Customer can flag specific transactions: "Is this really mule activity?"
2. Expert responds within 2 hours with:
   - Clear regulatory guidance
   - Why the label was applied (or adjusted)
   - References to FinCEN FAQs, FATF guidance
3. **Customer reaction:** "They actually understand AML regulations"
   - Builds trust that your labels are defensible
   - Creates ongoing relationship (not just transactional labeling)

---

## Part 4: What Makes This Lovable (The Design Philosophy)

### Principle 1: Expertise Visibility

Every design choice shows your regulatory knowledge.

**Examples:**
- **Label naming**: Not generic "category_1", but "aml_typology" aligned to FATF language
- **Confidence scores**: Not just "85% confident" but "0.87 inter-annotator agreement (Cohen's Kappa, our team of 3 independent reviewers)"
- **Explanations**: Show regulatory knowledge: "FATF R.7 identifies beneficial ownership gap; recipient cannot be linked to registered entity"
- **Dashboard**: Educates while informing: "Structuring (FATF): Multiple small transfers consolidated. Red flag for money laundering attempts."

**Customer feels**: "These people know AML regulations deeply"

### Principle 2: Transparency & Explainability

Never ask customers to trust a black box.

**Implementation:**
- Every transaction gets a reason code (not "suspicious", but "structuring_pattern + high_risk_jurisdiction")
- Audit trail shows: "Expert reviewer: [Name], Timestamp: [Date], Team consensus: [3 reviewers agreed]"
- Methodology documented: "Labels based on FATF R.10 typologies, FinCEN SAR guidance, COAF circular requirements"
- Confidence scoring: "This label has 95% inter-rater agreement; these edge cases have 60% agreement"

**Customer benefit**: Can defend labels to auditors, regulators, and their own leadership

### Principle 3: Simplicity Without Oversimplification

**What you DON'T do:**
- Show 50 features (configuration nightmare)
- Overwhelming dashboard with 100+ data points
- Jargon-heavy interface (regulators understand this, fintech non-compliance teams don't)

**What you DO do:**
- One clear flow: Upload → Review → Download audit-ready labels
- Confidence dashboard with 5 key metrics (not 50)
- Regulatory context built into every label
- Smart defaults (detect high-risk corridors automatically, users don't need to "configure")

### Principle 4: Consistency Creates Love

Compliance teams want to trust your service completely.

**How:**
- Same methodology applied to every transaction (never "sometimes we flag structuring, sometimes we don't")
- Audit trail shows consistency (timestamps, reviewer names, confidence scores)
- Regular methodology updates (when new regulations arrive, we update proactively)
- Versioning: "These labels use AML Methodology v2.1 (updated Nov 2025 for AMLA compliance)"

**Customer benefit**: No surprises, no inconsistencies, can rely on your labels completely

### Principle 5: Regulatory Defensibility Built In

**Every deliverable assumes**: "A regulator might audit how these labels were created"

**Implementation:**
- Audit report template includes: methodology, reviewer names, confidence scores, regulatory references
- Regulatory reference document links to actual FinCEN/COAF/AMLA documents
- Methodology versioning (what regulation version were these labels created under?)
- Hash verification (prove labels haven't been tampered with)

**Customer benefit**: Can show regulators your process is sound, labels are defensible

---

## Part 5: The Service Model (How You Deliver Expertise)

### Core Service: "Regulated Transaction Labeling"

**Model 1: Batch Processing (Primary)**
- Customer uploads CSV file with transactions
- Your team (currently: you + AI + 1-2 part-time reviewers) labels within 24 hours
- Delivers: CSV with labels + audit report
- Price: $0.012/transaction (high-risk corridors), $0.008/transaction (bulk volumes >50k)

**Why lovable:**
- Customers know exactly what they're getting (24-hour turnaround, specific price)
- Clear deliverable (audit-ready labels they can use immediately)
- Defensible methodology (regulatory reference document backs it up)

### Secondary Service: "Regulatory Edge Case Consultation" (Optional Add-On)

- Customer flags ambiguous transactions
- Expert provides regulatory guidance within 2 hours
- Clarifies label or suggests adjustment with reasoning
- Price: $200/hour (billed per consultation, typically 15-30 min per question)

**Why lovable:**
- Shows your team is available and expert
- Builds relationship beyond transactional labeling
- Customer feels supported by genuine experts
- Differentiates from impersonal platforms

### How to Deliver (Infrastructure)

**Team Structure (MLP Phase):**
- **You**: Regulatory expertise, label quality assurance, customer relationships
- **AI (GPT-4o with AML prompting)**: Auto-labels obvious cases (mule activity patterns, high-risk jurisdictions)
- **1-2 Part-time Reviewers**: Verify AI labels, apply expert judgment to edge cases
- **Phase 2 Infrastructure**: Job tracking, file processing, results delivery

**Workflow:**
1. Customer uploads CSV via API/Web
2. Phase 2 pipeline ingests data, applies Presidio PII redaction
3. AI labeling task: Custom AML prompting (not generic labeling)
4. Human review: You + reviewers verify, apply expertise to edge cases
5. Results assembly: Labels + confidence scores + reasoning + audit report
6. Delivery: CSV download + email notification

**Quality Gate:**
- You personally review random 20% sample
- All labels must have explicit reasoning (no unlabeled transactions)
- Confidence score ≥0.70 (agreement among reviewers) required before delivery
- Any label <0.70 agreement flagged for additional expert review

---

## Part 6: What You're Building (Scope of Work)

### Phase 1 Development: Weeks 1-4 (Adapt Phase 2 for AML)

**Modify existing Phase 2 code:**

1. **Labeling Task Specification** (Replace generic labeling in `ingestion.py`)
   - Input: Transaction data (sender_id, recipient_country, amount, timestamp)
   - AI Prompt: FATF-aligned AML typology extraction
   - Output: `aml_risk_level`, `aml_typology`, `regulatory_flag`, `expert_reasoning`
   - Estimated: 400 lines (replace generic labeling)

2. **Quality Assurance Task** (New: `aml_qa_task.py`)
   - Inter-annotator agreement calculation (Cohen's Kappa)
   - Confidence scoring logic
   - Edge case detection (low agreement → expert review)
   - Estimated: 300 lines

3. **Audit Report Generation** (New: `audit_report_generator.py`)
   - Summary statistics (transactions reviewed, flag rate, typology distribution)
   - Regulatory reference links (FinCEN SAR FAQ, FATF R.10, COAF circular)
   - Methodology documentation
   - Estimated: 250 lines

4. **API Response Enhancement** (Modify `jobs/contracts.py` + `jobs/router.py`)
   - Add AML-specific fields to JobStatusContract
   - Add audit report download endpoint
   - Estimated: 150 lines

5. **Regulatory Reference Integration**
   - Link to `REGULATORY_REFERENCE_AML_SERVICE.md` in audit reports
   - API endpoint: GET `/api/v1/regulatory-context` returns relevant guidance
   - Estimated: 100 lines

**Total: ~1,200 lines of new/modified code**
**Timeline: 2-3 weeks (with Phase 2 infrastructure as foundation)**

### Phase 2: Customer Interface (Weeks 4-6)

1. **Web interface** (if not existing):
   - Upload form (drag-drop CSV)
   - Scenario selector (cross-border transfers, sanctions evasion, trade-based ML)
   - Progress dashboard
   - Results download + audit report

2. **Email notification** with results link

3. **Confidence dashboard** (interactive visualization)
   - Risk level distribution
   - Top flagged typologies
   - Geographic patterns

**Can start with minimal UI (CSV upload via API + email) and upgrade to web UI in Phase 2**

### Phase 3: Go-to-Market (Weeks 6-8)

1. **Identify 5 early adopter fintechs**
   - Criteria: Raising Series A+, moving to ML-based AML, frustrated with current solutions
   - Outreach: "We're building regulatory expertise for AML labeling. Want to try it?"

2. **Run pilots** (free/heavily discounted)
   - 1,000-5,000 transactions labeled
   - Measure: Do they trust the labels? Would they recommend?
   - Iterate on UX based on feedback

3. **Document results** as case study
   - "FinTech Company X trained ML model with our labels"
   - "Reduced AML review time by 60%"
   - "Regulators had no questions about labeling methodology"

---

## Part 7: Why This Is Defensible (Not Competing on Features)

### You're Not Fighting Scale AI or Labelbox

| Dimension | Scale AI | Labelbox | Your AML Service |
|-----------|----------|----------|------------------|
| **Budget** | $15B (Meta-backed) | $189M funded | Lean startup |
| **Team size** | 500+ | 200+ | You + 1-2 reviewers |
| **Platform scope** | All labeling scenarios | All labeling scenarios | High-risk transactions only |
| **Competitive advantage** | Brand, capital, scale | Brand, platform lock-in | Regulatory expertise + trust |
| **Customer** | Every enterprise | Enterprises needing collab | Fintechs moving to ML-based AML |
| **TAM** | $40B (all labeling) | $40B (all labeling) | $800M (fintech AML only) |

**Why you win your segment:**
- Fintech compliance officers don't want a 500-person enterprise platform
- They want an expert team they can trust
- Your expertise (regulatory knowledge) is not Scale AI's core strength (theirs is scale)
- Your simplicity (focused scope) is an advantage, not a limitation

### The Fintech Advantage

**Why fintech is different from generic data labeling:**
1. **Regulatory pressure is existential** (8-figure OFAC fines in 2025)
2. **Expertise gap is real** (no vendor owns AML labeling like Scale owns image labeling)
3. **Community is tight** (one success = 5 referrals)
4. **They understand compliance cost** (willing to pay for reliability, not features)
5. **Regulatory defensibility matters** (they audit your methodology, not your features)

---

## Part 8: Pricing & Unit Economics

### Pricing Model

**Per-Transaction Pricing (with volume discounts):**

```
1-10,000 transactions:     $0.012/transaction
10,001-50,000 transactions: $0.010/transaction
50,000+ transactions:       $0.008/transaction

Regulatory Edge Case Consultation: $200/hour (min 15 min)
```

**Example customers:**
- Series A fintech labeling 10,000 transactions for first ML model: $120 (one-time)
- Series B fintech ongoing labeling 200,000/month: $1,600/month
- Scale fintech 2M/month: $16,000/month

### Unit Economics (Estimated)

**Per transaction cost (at scale):**
- AI labeling cost: $0.0015 (GPT-4o + prompt)
- Human review (20% of transactions): $0.0025
- Infrastructure + QA: $0.0010
- **Total cost: $0.005/transaction**

**At $0.012 per transaction:**
- Gross margin: 58% ($0.007 profit per transaction)
- At 100,000 transactions/month: $700 gross profit
- At 500,000 transactions/month: $3,500 gross profit
- At 2M transactions/month: $14,000 gross profit

**Sustainable at scale, but requires:**
- Volume (need 100k+ transactions/month to be profitable)
- Automation (AI must handle obvious cases; you focus on edge cases)
- Efficiency (can't spend 5 minutes per transaction in review)

### Go-to-Market Pricing

**Early adopter pricing (first 5 customers):**
- 50% discount off list price
- Unlimited regulatory consultations (build relationship)
- "Reference customer" agreement (can use in case studies)
- **Goal**: Get early proof points before scaling

---

## Part 9: Metrics for Lovability (What Success Looks Like)

### Technical Metrics

| Metric | Target | Why It Matters |
|--------|--------|---------------|
| **Labeling Accuracy** | 98%+ | Trust is paramount in compliance |
| **Inter-rater Agreement** | Cohen's Kappa ≥0.80 | Consistency = defensibility |
| **Label Explanation Quality** | 95% defendable to regulator | Expertise visibility |
| **Turnaround Time** | 24 hours or less | Promise kept = lovable |
| **Audit Trail Completeness** | 100% of labels documented | Regulatory defensibility |

### Customer Metrics

| Metric | Target | Why It Matters |
|--------|--------|---------------|
| **Net Promoter Score (NPS)** | 50+ | Indicates strong satisfaction |
| **Customer Recommendation** | 4/5 early adopters recommend | Word-of-mouth validation |
| **Label Trust Score** | "Would defend to regulator" | Main value proposition |
| **Feature Requests** | 0 (focused scope = no confusion) | Sign that MLP nails the job |
| **Retention** | 100% (year 1) | Lovable products don't churn |

### Business Metrics

| Metric | Target | Why It Matters |
|--------|--------|---------------|
| **Early Adopter Count** | 5-10 by month 6 | Validation of market fit |
| **Repeat Customer Rate** | 80%+ | Stickiness |
| **Average Customer LTV** | $5,000-15,000/year | Unit economics |
| **Sales Cycle** | 2-4 weeks | Fintech decision-making speed |

---

## Part 10: Risk Mitigation (What Could Go Wrong)

### Risk 1: Accuracy Degradation Under Scale
**Problem**: What works at 10k transactions/month breaks at 100k/month
**Mitigation**:
- Don't scale without increasing human review
- Use confidence scoring to flag low-agreement labels (don't ship if <0.70 agreement)
- Quarterly methodology reviews (catch drift early)
- **Lovability boundary**: Accuracy > volume. Turn away transactions if quality suffers

### Risk 2: Regulatory Landscape Changes
**Problem**: New AMLA guidance changes your labeling approach
**Mitigation**:
- Quarterly regulatory scanning (monitor FinCEN, COAF, AMLA releases)
- Version your methodology ("AML Labels v2.1, updated Nov 2025 for AMLA compliance")
- Proactive customer communication ("We're updating our approach for X new regulation")
- **Competitive advantage**: Be faster than competitors at implementing regulatory changes

### Risk 3: Customers Want More Features
**Problem**: "Can you also do KYC labeling? Ongoing monitoring? Sanctions screening?"
**Mitigation**:
- Explicitly scope MLP to 3 specific scenarios (high-risk corridors, sanctions evasion, trade-based ML)
- Position as "We're experts at X; others do everything"
- When customers request new features: "That's a great idea. We're focused on transaction screening right now, but let us know if there's demand"
- **Lovability boundary**: Stay focused. Generalization kills expertise positioning

### Risk 4: Competitor Response
**Problem**: Labelbox or Scale AI add "AML expertise"
**Mitigation**:
- You can't compete on features or budget
- Your advantage: Deep, documented regulatory expertise + fintech relationships
- Move fast to establish fintech market position before they respond
- Build moat through customer relationships, not platform lock-in
- **Lovability boundary**: Your team's reputation is the moat, not your code

---

## Part 11: Success Criteria (What Triggers Scaling vs Pivoting)

### Lovability Validation (By Month 4)

**Go/No-Go: Do early adopters love this?**

**Go Signals** (scale to next phase):
- ✅ 4+ early adopters completing pilots
- ✅ NPS 50+ (willing to recommend)
- ✅ 100% accuracy on test samples
- ✅ Zero "I don't trust this label" feedback
- ✅ At least 2 customers explicitly requesting ongoing service

**No-Go Signals** (pivot or reposition):
- ❌ Accuracy <95% (trust broken)
- ❌ NPS <40 (not lovable enough)
- ❌ Customers confused about labeling methodology
- ❌ Regulatory defensibility questioned
- ❌ Customers want features outside your scope

**If No-Go**: Pivot to different vertical (fintech was good for learning, maybe healthcare/legal has better fit) or different positioning (quality assurance rather than compliance expertise)

### Scaling Validation (By Month 8)

**Assumptions to test:**
- Unit economics hold at 100k+ transactions/month
- Sales cycle is 2-4 weeks (not 3 months)
- Customer acquisition cost <$5,000 (CAC)
- LTV:CAC ratio >3:1 (sustainable growth)
- Regulatory landscape doesn't fundamentally shift

**If validated**: Hire second expert reviewer, scale to 500k-1M transactions/month, expand to second AML scenario (ongoing transaction monitoring)

**If not validated**: Optimize unit economics, extend sales cycle, re-evaluate market fit

---

## Part 12: Timeline & Milestones

### Month 1 (Weeks 1-4): Build the MLP

**Week 1-2:**
- Adapt Phase 2 labeling task for AML (1,200 lines of code)
- Create AML prompting for AI (test with 100 sample transactions)
- Set up human review workflow (you + 1 part-time reviewer)

**Week 3:**
- Manually test with 1,000 transactions (compare human labels to AI)
- Measure accuracy and inter-rater agreement
- Iterate on AML prompting based on results
- Create audit report template

**Week 4:**
- Deploy to staging environment
- Internal testing (label 500 transactions, measure quality)
- Prepare regulatory reference integration
- Create customer onboarding flow

### Month 2 (Weeks 5-8): Test with Early Adopters

**Week 5-6:**
- Identify and contact 10 potential early adopters
- Frame as "beta program" (free/heavily discounted)
- Goal: Get 3 pilots signed up

**Week 7-8:**
- Run first 3 pilots (1,000-5,000 transactions each)
- Measure NPS, accuracy, customer sentiment
- Iterate on UX based on feedback
- Document results

### Month 3 (Weeks 9-12): Refine & Scale Early Adopters

**Week 9-10:**
- Incorporate feedback from pilots
- Recruit 2-3 more early adopters
- Establish pricing ($0.012/transaction starting point)

**Week 11-12:**
- Run 5-8 pilots (total)
- Measure: Do customers want ongoing service?
- Prepare "go/no-go" decision point

**Decision Point: By end of Month 3, decide:**
- Scale to next phase (hire second reviewer, expand scope)
- Pivot to different vertical
- Extend timeline (continue learning)

---

## Appendix A: Minimum Lovable Core (One Page)

**For quick reference:**

### What You're Selling
- Transaction labeling aligned to FATF AML typologies
- For fintech companies building ML-based AML systems
- Delivered with regulatory expertise and explicit reasoning

### Who You're Selling To
- Series A+ fintechs with 100k+ monthly transactions
- Compliance teams frustrated with manual labeling
- Companies moving from rules-based to ML-based AML

### What Makes It Lovable
1. **Expertise visibility**: Every label shows regulatory knowledge
2. **Regulatory defensibility**: Can explain labels to auditors
3. **Consistency**: Same methodology applied to every transaction
4. **Simplicity**: Upload → Label → Download (no configuration)
5. **Transparency**: Explicit reasoning for every decision

### What You're NOT Building
- ❌ Platform with 50 features
- ❌ KYC labeling or customer due diligence
- ❌ Real-time transaction monitoring
- ❌ Competing with Labelbox or Scale AI on features

### MLP Success Metrics
- **NPS 50+** (customers recommend)
- **Accuracy 98%+** (labels are trustworthy)
- **Turnaround <24 hours** (promise kept)
- **4+ early adopters** (market validation)
- **Zero regulatory defensibility questions** (expertise proven)

---

## Appendix B: Customer Interview Guide (For Early Adopter Recruitment)

**Goal**: Find 5 fintechs who are:
1. Building ML-based AML systems
2. Frustrated with manual transaction labeling
3. Willing to trust a new vendor with compliance data

**Outreach Message:**
> "Hi [Name], I'm building a regulatory expertise service for fintech companies labeling transaction data for AML compliance. We're working with early adopters to validate the approach. Would 20 minutes to discuss your current labeling process?"

**Key Questions:**
1. "How are you currently labeling transaction data for your ML model?"
2. "What's the biggest frustration with your current approach?"
3. "Would you trust a small team of AML experts to label your data if we could explain every decision?"
4. "How much would you save if labeling took 24 hours instead of 4 weeks?"
5. "Would you want to be part of our early adopter program?"

**Target Profiles:**
- Series A/B fintech (500k-5M in annual transactions)
- Raising money or deploying ML models
- Budget for compliance tooling ($2-20k/month)

---

## Conclusion

This MLP is **NOT a compromise**. It's a strategic choice to compete where you have unfair advantage (regulatory expertise) rather than where you'll always lose (platform features).

**The thesis:**
- Fintech compliance officers don't want another platform
- They want to trust a team that understands AML regulations
- Your competitive advantage is expertise, delivered lovably
- Focus on one scenario, own it completely, then expand

**Success looks like:**
- Early adopters saying "I recommend Data Foundry to everyone"
- Regulators asking "How do you ensure label quality?" and getting a clear answer
- Your team becoming known as the fintech AML labeling experts

**Lovable > Viable. Always.**

---

**Document Version:** 1.0
**Next Review:** After first 3 customer pilots (Month 2)
**Owner:** Data Foundry Product Team
