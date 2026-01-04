# Spend Intelligence Dashboard - Implementation Roadmap

## Overview
This document outlines the 3-phase implementation plan to build the Spend Intelligence Dashboard, an AI Unit Economics Platform that helps AI SaaS companies understand which customers are profitable, which are bleeding margin, and how to price for growth.

**The Approach:** Concierge MVP → Automated MVP → Full Product

**Timeline:** 24 weeks (6 months)

**Target Market:** AI SaaS companies with $50K+/mo LLM spend

**Competitive Positioning:** Based on competitive intelligence research (January 2026), this product occupies a unique white space between LLM observability tools (Helicone, Langfuse, Braintrust) and cloud cost management platforms (CloudZero). No competitor currently offers customer-level margin analysis with Stripe revenue integration.

**Key Differentiators:**
- Customer-level cost aggregation (Stripe meter events → customer costs)
- Margin calculation (cost-to-serve vs. revenue per customer)
- Anomaly detection on usage patterns (baseline vs. current)
- Peer benchmarking (anonymous comparison across customers)
- Slack/email alerts on margin compression
- PDF export for CFO reviews

---

## Phase 1: Concierge MVP (Weeks 1-4)

### Goal
Validate demand with 5-10 early adopters at $99/mo

### What We Build

#### Manual Customer Onboarding (Week 1)
**Objective:** Set up first customers manually to validate the value proposition

**Tasks:**
- Hand-crafted SQL queries to aggregate meter events by customer
- Manual Stripe revenue fetch via Stripe CLI
- Excel/Google Sheets for margin calculation
- One-time setup per customer (2-3 hours)

**Deliverables:**
- SQL query library for customer cost aggregation
- Stripe CLI command reference
- Excel template for margin calculation
- Onboarding checklist

**Tools:**
- PostgreSQL queries (metering service database)
- Stripe CLI (`stripe invoices list`, `stripe subscriptions list`)
- Google Sheets (data visualization)

#### Weekly Email Reports (Week 1-2)
**Objective:** Deliver actionable margin insights to customers weekly

**Tasks:**
- Manual aggregation of customer costs
- Calculate margins (cost-to-serve vs. revenue)
- Format as PDF report
- Email to CFO weekly

**Report Structure:**
1. Executive Summary (total cost, revenue, margin)
2. Customer P&L (top 10 customers by revenue)
3. Unprofitable Customers (margin < 20%)
4. Cost Breakdown by Model (GPT-4, Claude, etc.)
5. Week-over-Week Trends

**Deliverables:**
- PDF report template
- Weekly delivery process
- Customer feedback loop

#### Customer Cost Aggregation Script (Week 2)
**Objective:** Automate manual SQL queries with Python script

**Script Features:**
- Fetch meter events from Metering Service API
- Aggregate by customer (stripe_customer_id)
- Calculate cost breakdown by model, endpoint
- Output: CSV file

**Pseudo-code:**
```python
# Fetch meter events from last 7 days
events = metering_api.get_meter_events(
    start_date=today - 7 days,
    end_date=today
)

# Aggregate by customer
customer_costs = defaultdict(lambda: {
    'total_cost': 0,
    'costs_by_model': defaultdict(float),
    'costs_by_endpoint': defaultdict(float)
})

for event in events:
    customer_id = event.stripe_customer_id
    cost = event.quantity * event.unit_price
    customer_costs[customer_id]['total_cost'] += cost
    customer_costs[customer_id]['costs_by_model'][event.model] += cost
    customer_costs[customer_id]['costs_by_endpoint'][event.endpoint] += cost

# Export to CSV
export_to_csv(customer_costs, 'customer_costs.csv')
```

**Deliverables:**
- Python script (`aggregate_customer_costs.py`)
- CSV output format specification
- Error handling and logging

#### Margin Calculation Script (Week 2)
**Objective:** Calculate customer margins by matching costs to Stripe revenue

**Script Features:**
- Fetch Stripe revenue data (subscriptions, invoices)
- Match meter event costs to Stripe customers
- Calculate margin percentages
- Identify unprofitable customers (margin < 20%)
- Output: CSV file

**Pseudo-code:**
```python
# Load customer costs
customer_costs = load_csv('customer_costs.csv')

# Fetch Stripe revenue
stripe_customers = stripe_api.list_customers()
for customer in stripe_customers:
    subscriptions = stripe_api.list_subscriptions(customer.id)
    invoices = stripe_api.list_invoices(customer.id)

    # Calculate MRR
    mrr = sum(sub.price for sub in subscriptions if sub.status == 'active')

    # Calculate margin
    cost = customer_costs[customer.id]['total_cost']
    margin_percent = ((mrr - cost) / mrr) * 100 if mrr > 0 else 0

    customer_costs[customer.id]['revenue'] = mrr
    customer_costs[customer.id]['margin_percent'] = margin_percent
    customer_costs[customer.id]['is_profitable'] = margin_percent >= 20

# Export to CSV
export_to_csv(customer_costs, 'customer_margins.csv')
```

**Deliverables:**
- Python script (`calculate_margins.py`)
- CSV output format specification
- Margin threshold configuration (20% default)

#### Google Sheets Dashboard (Week 3)
**Objective:** Create simple, shareable dashboard for customers

**Tasks:**
- Import CSV data (customer_costs.csv, customer_margins.csv)
- Create pivot tables for cost breakdown
- Calculate margins
- Visualizations: Cost per customer, margin % trends
- Share with CFO via link

**Dashboard Structure:**
1. **Summary Tab**
   - Total customers
   - Average margin %
   - Unprofitable customer count
   - Total cost vs. revenue

2. **Customer P&L Tab**
   - Table: Customer ID, Revenue, Cost, Margin %, Status
   - Filters: Profitable/Unprofitable
   - Sort: By margin %, by revenue

3. **Cost Breakdown Tab**
   - Pivot table: Costs by model (GPT-4, Claude, etc.)
   - Pivot table: Costs by endpoint
   - Charts: Cost distribution

4. **Trends Tab**
   - Line chart: Margin % over time
   - Bar chart: Top 10 customers by cost

**Deliverables:**
- Google Sheets template
- Import automation (Google Sheets API or manual)
- Sharing permissions setup

#### Baseline Calculation Script (Week 3)
**Objective:** Calculate baseline usage for anomaly detection

**Script Features:**
- Calculate 30-day rolling average usage per customer
- Store in simple database (SQLite)
- Output: baseline_values.csv

**Pseudo-code:**
```python
# Fetch meter events from last 30 days
events = metering_api.get_meter_events(
    start_date=today - 30 days,
    end_date=today
)

# Calculate baseline per customer
baselines = {}
for customer_id in unique_customers(events):
    customer_events = [e for e in events if e.stripe_customer_id == customer_id]

    # Calculate daily averages
    daily_costs = defaultdict(float)
    for event in customer_events:
        cost = event.quantity * event.unit_price
        daily_costs[event.date] += cost

    # Rolling average
    baseline_cost = sum(daily_costs.values()) / 30

    baselines[customer_id] = {
        'baseline_daily_cost': baseline_cost,
        'baseline_total_cost': baseline_cost * 30,
        'calculation_date': today
    }

# Store in SQLite
db.store_baselines(baselines)
export_to_csv(baselines, 'baseline_values.csv')
```

**Deliverables:**
- Python script (`calculate_baselines.py`)
- SQLite database schema
- CSV output format

#### Manual Anomaly Detection (Week 4)
**Objective:** Flag usage anomalies for customer review

**Process:**
1. Weekly manual review: Compare current usage vs. baseline
2. Flag anomalies: >20% deviation
3. Email summary to CFO

**Anomaly Detection Logic:**
```python
# Fetch current week costs
current_costs = load_csv('customer_costs.csv')

# Load baselines
baselines = load_csv('baseline_values.csv')

# Detect anomalies
anomalies = []
for customer_id in current_costs:
    current_cost = current_costs[customer_id]['total_cost']
    baseline_cost = baselines[customer_id]['baseline_total_cost']

    deviation_percent = ((current_cost - baseline_cost) / baseline_cost) * 100

    if abs(deviation_percent) > 20:
        anomalies.append({
            'customer_id': customer_id,
            'current_cost': current_cost,
            'baseline_cost': baseline_cost,
            'deviation_percent': deviation_percent,
            'type': 'SPIKE' if deviation_percent > 0 else 'DROP'
        })

# Email summary
send_email('cfo@company.com', 'Weekly Anomaly Report', anomalies)
```

**Deliverables:**
- Python script (`detect_anomalies.py`)
- Email template for anomaly reports
- Anomaly threshold configuration (20% default)

### What We Sell

**Target:** 5-10 AI SaaS companies with $50K+/mo LLM spend

**Customer Profile:**
- B2B AI SaaS (not B2C)
- Raised funding (Seed/Series A)
- Using Stripe for payments
- Visible LLM usage (blog posts, case studies)
- 50+ customers
- $10K+/mo MRR

**Outreach Strategy:**
1. **Cold Email to 200 AI SaaS Companies**
   - Source: Crunchbase (raised funding), Product Hunt (AI tools), LinkedIn (AI SaaS groups)
   - Filter by: Raised funding, using Stripe, visible LLM usage
   - Offer: "We'll show you which customers are profitable for $99/mo"

2. **Email Template:**
   ```
   Subject: Which of your customers are profitable?

   Hi [Name],

   I'm building a tool for AI SaaS companies to calculate customer-level margins.
   Most AI SaaS founders I talk to don't know which customers are profitable and which are bleeding margin.

   I'll manually aggregate your meter events, match them to Stripe revenue, and send you a weekly report showing:
   - Which customers are profitable (margin > 20%)
   - Which customers are unprofitable (margin < 20%)
   - Cost breakdown by model (GPT-4, Claude, etc.)

   Intro pricing: $99/mo (locked for 12 months).
   I'm onboarding 5-10 companies this month.

   Want to see a sample report?

   [Your Name]
   ```

3. **Follow-up Sequence:**
   - Day 0: Initial email
   - Day 3: Follow-up with sample report (anonymized)
   - Day 7: Final call-to-action

**Onboarding Process:**
1. **Discovery Call (15 min)**
   - Understand customer list (how many customers)
   - Understand LLM usage (which models, endpoints)
   - Collect API keys (Stripe, Metering Service)

2. **Manual Setup (2-3 hours)**
   - Run cost aggregation script
   - Run margin calculation script
   - Generate first report (PDF)
   - Set up Google Sheets dashboard

3. **First Report (Within 48 hours)**
   - Email PDF report
   - Share Google Sheets link
   - Schedule feedback call (30 min)

4. **Weekly Delivery (Ongoing)**
   - Run scripts every Monday
   - Email PDF report by Tuesday
   - Update Google Sheets dashboard

**Pricing:** $99/mo (intro pricing, locked for 12 months)

**Payment:** Stripe subscription (manual setup)

### Deliverables
- [ ] 5-10 paying customers
- [ ] $500-1,000 MRR
- [ ] 3-5 case studies
- [ ] Validated demand

### Success Criteria
- 3+ customers by week 4
- At least 1 customer says "This is worth 10x what I'm paying"
- 2+ customers willing to provide case study

### Go/No-Go Decision
**End of Week 4:** If <3 customers, pivot or iterate on value proposition

---

## Phase 2: Automated MVP (Weeks 5-12)

### Goal
Self-service product with $199-299/mo pricing, 20-30 customers

### What We Build

#### Analytics API (Weeks 5-6)
**Objective:** Build REST API for cost aggregation and margin calculation

**Tech Stack:**
- Python (FastAPI or Flask)
- PostgreSQL (metering service database)
- Stripe API (revenue data)

**Endpoint 1: GET /analytics/customers/{id}/margins**
- **Description:** Fetch margin data for a specific customer
- **Parameters:**
  - `id`: Stripe customer ID
  - `start_date`: Optional (default: 30 days ago)
  - `end_date`: Optional (default: today)
- **Response:**
  ```json
  {
    "customer_id": "cus_123",
    "period": {
      "start_date": "2026-01-01",
      "end_date": "2026-01-31"
    },
    "cost": {
      "total": 1250.50,
      "by_model": {
        "gpt-4": 850.00,
        "claude-3-opus": 400.50
      },
      "by_endpoint": {
        "/api/chat": 1000.00,
        "/api/analyze": 250.50
      }
    },
    "revenue": {
      "mrr": 2500.00,
      "invoices": [
        {
          "id": "in_123",
          "amount": 2500.00,
          "status": "paid"
        }
      ]
    },
    "margin": {
      "amount": 1249.50,
      "percent": 49.98
    },
    "status": "profitable"
  }
  ```

**Endpoint 2: GET /analytics/customers/{id}/costs**
- **Description:** Fetch cost breakdown for a specific customer
- **Parameters:**
  - `id`: Stripe customer ID
  - `start_date`: Optional (default: 30 days ago)
  - `end_date`: Optional (default: today)
  - `group_by`: Optional (model, endpoint, default: both)
- **Response:**
  ```json
  {
    "customer_id": "cus_123",
    "period": {
      "start_date": "2026-01-01",
      "end_date": "2026-01-31"
    },
    "total_cost": 1250.50,
    "costs_by_model": [
      {
        "model": "gpt-4",
        "cost": 850.00,
        "percent": 67.98
      },
      {
        "model": "claude-3-opus",
        "cost": 400.50,
        "percent": 32.02
      }
    ],
    "costs_by_endpoint": [
      {
        "endpoint": "/api/chat",
        "cost": 1000.00,
        "percent": 79.96
      },
      {
        "endpoint": "/api/analyze",
        "cost": 250.50,
        "percent": 20.04
      }
    ],
    "trends": {
      "30_days": 1250.50,
      "60_days": 2400.00,
      "90_days": 3600.00
    }
  }
  ```

**Endpoint 3: GET /analytics/customers/{id}/revenue**
- **Description:** Fetch Stripe revenue data for a specific customer
- **Parameters:**
  - `id`: Stripe customer ID
  - `start_date`: Optional (default: 30 days ago)
  - `end_date`: Optional (default: today)
- **Response:**
  ```json
  {
    "customer_id": "cus_123",
    "period": {
      "start_date": "2026-01-01",
      "end_date": "2026-01-31"
    },
    "mrr": 2500.00,
    "subscriptions": [
      {
        "id": "sub_123",
        "status": "active",
        "price": 2500.00,
        "interval": "month"
      }
    ],
    "invoices": [
      {
        "id": "in_123",
        "amount": 2500.00,
        "status": "paid",
        "created": "2026-01-15"
      }
    ]
  }
  ```

**Deliverables:**
- FastAPI application with 3 endpoints
- API documentation (OpenAPI/Swagger)
- Error handling and logging
- Unit tests (50+ test cases)

#### Margin Calculation Engine (Week 7)
**Objective:** Build batch job system for daily margin calculation

**Architecture:**
- **Batch Job 1:** Aggregate meter events by customer (daily)
- **Batch Job 2:** Fetch Stripe revenue data (daily)
- **Batch Job 3:** Calculate margins and store in database (daily)

**Database Schema:**
```sql
-- Customer costs table
CREATE TABLE customer_costs (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    cost_date DATE NOT NULL,
    total_cost DECIMAL(10, 2) NOT NULL,
    costs_by_model JSONB NOT NULL,
    costs_by_endpoint JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, cost_date)
);

CREATE INDEX idx_customer_costs_customer_date ON customer_costs(customer_id, cost_date);

-- Margin reports table
CREATE TABLE margin_reports (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    report_date DATE NOT NULL,
    revenue DECIMAL(10, 2) NOT NULL,
    cost DECIMAL(10, 2) NOT NULL,
    margin DECIMAL(10, 2) NOT NULL,
    margin_percent DECIMAL(5, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, report_date)
);

CREATE INDEX idx_margin_reports_customer_date ON margin_reports(customer_id, report_date);
```

**Batch Job Logic:**
```python
# Batch Job 1: Aggregate meter events
def aggregate_meter_events():
    events = db.query("""
        SELECT stripe_customer_id, meter_name, quantity, unit_price, created_at
        FROM meter_events
        WHERE DATE(created_at) = CURRENT_DATE - INTERVAL '1 day'
    """)

    customer_costs = defaultdict(lambda: {
        'total_cost': 0,
        'costs_by_model': {},
        'costs_by_endpoint': {}
    })

    for event in events:
        cost = event.quantity * event.unit_price
        customer_costs[event.stripe_customer_id]['total_cost'] += cost
        customer_costs[event.stripe_customer_id]['costs_by_model'][event.meter_name] = \
            customer_costs[event.stripe_customer_id]['costs_by_model'].get(event.meter_name, 0) + cost

    # Store in database
    for customer_id, costs in customer_costs.items():
        db.insert('customer_costs', {
            'customer_id': customer_id,
            'cost_date': yesterday,
            'total_cost': costs['total_cost'],
            'costs_by_model': json.dumps(costs['costs_by_model']),
            'costs_by_endpoint': json.dumps(costs['costs_by_endpoint'])
        })

# Batch Job 2: Fetch Stripe revenue
def fetch_stripe_revenue():
    customers = stripe.Customer.list()

    for customer in customers:
        subscriptions = stripe.Subscription.list(customer=customer.id, status='active')
        mrr = sum(sub.price for sub in subscriptions)

        # Store in margin_reports table
        db.insert_or_update('margin_reports', {
            'customer_id': customer.id,
            'report_date': today,
            'revenue': mrr
        })

# Batch Job 3: Calculate margins
def calculate_margins():
    reports = db.query("""
        SELECT
            mr.customer_id,
            mr.report_date,
            mr.revenue,
            COALESCE(cc.total_cost, 0) as cost
        FROM margin_reports mr
        LEFT JOIN customer_costs cc
            ON mr.customer_id = cc.customer_id
            AND mr.report_date = cc.cost_date
        WHERE mr.report_date = CURRENT_DATE
    """)

    for report in reports:
        margin = report.revenue - report.cost
        margin_percent = (margin / report.revenue * 100) if report.revenue > 0 else 0
        status = 'profitable' if margin_percent >= 20 else 'unprofitable'

        db.update('margin_reports', {
            'cost': report.cost,
            'margin': margin,
            'margin_percent': margin_percent,
            'status': status
        }, {
            'customer_id': report.customer_id,
            'report_date': report.report_date
        })
```

**Scheduling:**
- Use Celery or simple cron jobs
- Run daily at 2 AM UTC
- Error notifications via Slack/email

**Deliverables:**
- Batch job scripts (Python)
- Database migrations
- Monitoring and alerting
- Unit tests (30+ test cases)

#### Anomaly Detection Service (Weeks 8-9)
**Objective:** Build automated anomaly detection system

**Architecture:**
- **Baseline Calculation:** 30-day rolling average per customer
- **Detection Job:** Hourly comparison of current usage vs. baseline
- **Statistical Analysis:** Z-score > 2 indicates anomaly

**Database Schema:**
```sql
-- Baseline values table
CREATE TABLE baseline_values (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    baseline_date DATE NOT NULL,
    baseline_daily_cost DECIMAL(10, 2) NOT NULL,
    baseline_total_cost DECIMAL(10, 2) NOT NULL,
    calculation_window INTEGER NOT NULL DEFAULT 30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, baseline_date)
);

CREATE INDEX idx_baseline_values_customer_date ON baseline_values(customer_id, baseline_date);

-- Anomalies table
CREATE TABLE anomalies (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    anomaly_date TIMESTAMP NOT NULL,
    current_cost DECIMAL(10, 2) NOT NULL,
    baseline_cost DECIMAL(10, 2) NOT NULL,
    deviation_percent DECIMAL(5, 2) NOT NULL,
    z_score DECIMAL(5, 2) NOT NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_anomalies_customer_date ON anomalies(customer_id, anomaly_date);
```

**Anomaly Detection Logic:**
```python
# Baseline Calculation
def calculate_baselines():
    customers = db.query("SELECT DISTINCT customer_id FROM customer_costs")

    for customer in customers:
        # Fetch last 30 days of costs
        costs = db.query("""
            SELECT cost_date, total_cost
            FROM customer_costs
            WHERE customer_id = %s
            AND cost_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY cost_date DESC
            LIMIT 30
        """, (customer.customer_id,))

        if len(costs) < 7:
            continue  # Not enough data

        # Calculate rolling average
        baseline_daily_cost = sum(c.total_cost for c in costs) / len(costs)
        baseline_total_cost = baseline_daily_cost * 30

        # Store baseline
        db.insert_or_update('baseline_values', {
            'customer_id': customer.customer_id,
            'baseline_date': today,
            'baseline_daily_cost': baseline_daily_cost,
            'baseline_total_cost': baseline_total_cost,
            'calculation_window': 30
        })

# Anomaly Detection
def detect_anomalies():
    customers = db.query("SELECT DISTINCT customer_id FROM baseline_values")

    for customer in customers:
        # Fetch today's cost
        current_cost = db.query("""
            SELECT COALESCE(total_cost, 0) as cost
            FROM customer_costs
            WHERE customer_id = %s AND cost_date = CURRENT_DATE
        """, (customer.customer_id,))

        if not current_cost:
            continue

        current_cost = current_cost[0].cost

        # Fetch baseline
        baseline = db.query("""
            SELECT baseline_daily_cost, baseline_total_cost
            FROM baseline_values
            WHERE customer_id = %s
            ORDER BY baseline_date DESC
            LIMIT 1
        """, (customer.customer_id,))

        if not baseline:
            continue

        baseline_cost = baseline[0].baseline_daily_cost

        # Calculate deviation
        deviation_percent = ((current_cost - baseline_cost) / baseline_cost) * 100

        # Calculate z-score (simplified)
        std_dev = db.query("""
            SELECT STDDEV(total_cost)
            FROM customer_costs
            WHERE customer_id = %s
            AND cost_date >= CURRENT_DATE - INTERVAL '30 days'
        """, (customer.customer_id,))[0].stddev or 1

        z_score = (current_cost - baseline_cost) / std_dev

        # Detect anomaly
        if abs(deviation_percent) > 20 and abs(z_score) > 2:
            anomaly_type = 'SPIKE' if deviation_percent > 0 else 'DROP'
            severity = 'HIGH' if abs(z_score) > 3 else 'MEDIUM'

            db.insert('anomalies', {
                'customer_id': customer.customer_id,
                'anomaly_date': now(),
                'current_cost': current_cost,
                'baseline_cost': baseline_cost,
                'deviation_percent': deviation_percent,
                'z_score': z_score,
                'anomaly_type': anomaly_type,
                'severity': severity
            })
```

**Scheduling:**
- Baseline calculation: Daily at 3 AM UTC
- Anomaly detection: Hourly
- Alert generation: Real-time

**Deliverables:**
- Anomaly detection scripts
- Database migrations
- Monitoring and alerting
- Unit tests (40+ test cases)

#### Alerting System (Week 10)
**Objective:** Build alert notification system

**Alert Types:**
1. **Margin Compression Alert:** Margin drops >20% week-over-week
2. **Usage Spike Alert:** Daily cost >2x baseline
3. **Unprofitable Customer Alert:** New customer falls below 20% margin
4. **Anomaly Alert:** Statistical anomaly detected

**Alert Channels:**
- Slack (webhook)
- Email (SMTP)
- SMS (optional, Twilio integration)

**Database Schema:**
```sql
-- Alert configurations table
CREATE TABLE alert_configurations (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    threshold_value DECIMAL(10, 2) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    channels JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alert history table
CREATE TABLE alert_history (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    alert_date TIMESTAMP NOT NULL,
    message TEXT NOT NULL,
    channels JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Alert Logic:**
```python
# Check margin compression
def check_margin_compression():
    reports = db.query("""
        SELECT
            customer_id,
            report_date,
            margin_percent,
            LAG(margin_percent) OVER (PARTITION BY customer_id ORDER BY report_date) as prev_margin_percent
        FROM margin_reports
        WHERE report_date >= CURRENT_DATE - INTERVAL '7 days'
    """)

    for report in reports:
        if report.prev_margin_percent:
            change = ((report.margin_percent - report.prev_margin_percent) / report.prev_margin_percent) * 100

            if change < -20:  # Margin compressed by 20%
                send_alert(
                    customer_id=report.customer_id,
                    alert_type='MARGIN_COMPRESSION',
                    message=f"Margin dropped from {report.prev_margin_percent}% to {report.margin_percent}% ({change:.1f}%)",
                    severity='HIGH'
                )

# Send alert to configured channels
def send_alert(customer_id, alert_type, message, severity):
    # Fetch alert configuration
    config = db.query("""
        SELECT channels
        FROM alert_configurations
        WHERE customer_id = %s AND alert_type = %s AND enabled = TRUE
    """, (customer_id, alert_type))

    if not config:
        return

    channels = config[0].channels

    # Send to Slack
    if channels.get('slack_enabled'):
        slack_webhook = channels.get('slack_webhook_url')
        send_slack_alert(slack_webhook, {
            'text': f"[{severity}] {alert_type}: {message}",
            'attachments': [{
                'color': 'danger' if severity == 'HIGH' else 'warning',
                'fields': [
                    {'title': 'Customer', 'value': customer_id},
                    {'title': 'Message', 'value': message}
                ]
            }]
        })

    # Send to Email
    if channels.get('email_enabled'):
        email = channels.get('email_address')
        send_email_alert(
            to=email,
            subject=f"[{severity}] {alert_type} Alert",
            body=message
        )

    # Log to alert history
    db.insert('alert_history', {
        'customer_id': customer_id,
        'alert_type': alert_type,
        'alert_date': now(),
        'message': message,
        'channels': json.dumps(channels),
        'status': 'sent'
    })
```

**Deliverables:**
- Alert notification system
- Alert configuration UI (simple form)
- Email templates
- Slack integration
- Alert history tracking

#### Basic Dashboard UI (Weeks 11-12)
**Objective:** Build simple, self-service dashboard

**Tech Stack:**
- React (frontend)
- Tailwind CSS (styling)
- Recharts (charts)
- FastAPI (backend API)

**Page 1: Customer List**
- **Table:** All customers with cost, revenue, margin, status
- **Filters:** Profitable/unprofitable, sort by margin
- **Drill-down:** Click customer for details

**Features:**
- Search by customer ID or name
- Filter by status (profitable/unprofitable)
- Sort by revenue, cost, margin percent
- Pagination (50 customers per page)
- Export to CSV

**Page 2: Customer Detail**
- **Cost Breakdown:** By model, endpoint
- **Revenue:** From Stripe (subscriptions, invoices)
- **Margin Trend Chart:** 30 days
- **Comparison to Peers:** Benchmarking (placeholder for Phase 3)

**Features:**
- Date range picker (7, 30, 60, 90 days)
- Cost breakdown pie chart
- Margin trend line chart
- Revenue bar chart
- Top endpoints by cost
- Top models by cost

**Page 3: Alerts**
- **List:** Recent anomalies
- **Configuration Form:** Set thresholds
- **Acknowledge:** Mark alerts as reviewed

**Features:**
- Alert history table
- Filter by alert type, severity
- Acknowledge alerts
- Configure alert thresholds
- Enable/disable channels (Slack, email)

**Authentication:**
- Stripe Connect (OAuth)
- Customer login via Stripe
- Row-level security (customer sees only their data)

**Deliverables:**
- React application with 3 pages
- API integration
- Authentication (Stripe Connect)
- Responsive design
- Unit tests (30+ test cases)

### What We Sell

**Pricing Tiers:**

| Plan | Price | Customers | Features | Alerts | Benchmarking |
|------|-------|-----------|----------|--------|--------------|
| **Starter** | $199/mo | Up to 50 | Cost aggregation, margin calculation, basic dashboard | Email only | ❌ |
| **Pro** | $299/mo | Unlimited | All Starter features + customer detail pages, trends | Slack + Email | ❌ (placeholder) |

**Launch Strategy:**

1. **Product Hunt Launch (Week 11)**
   - Target: 150+ upvotes, top 15 product of the day
   - Prepare: Screenshots, demo video, tagline
   - Tagline: "See which customers are profitable (and which are bleeding margin)"
   - Offer: 50% off first 100 customers (first month only)

2. **Case Studies from Phase 1**
   - Create 3-5 case studies
   - Format: Problem → Solution → Results
   - Example: "How [Company] saved $2K/month by fixing unprofitable segment"
   - Distribute via: Blog, Twitter, LinkedIn

3. **Self-Service Onboarding**
   - Stripe Connect integration (5-minute setup)
   - Onboarding flow: Connect Stripe → Select customers → View dashboard
   - First report: Available within 24 hours
   - Tutorial videos: 3-5 short clips (2-3 min each)

**Marketing Channels:**

1. **AI SaaS Communities**
   - AI Engineer Slack (10K+ members)
   - LLM Operators Discord (5K+ members)
   - YC Startup School forums
   - Indie Hackers

2. **Content Marketing**
   - Blog series: "AI SaaS Unit Economics"
     - Article 1: "Why AI SaaS companies have thin margins"
     - Article 2: "How to calculate cost-to-serve per customer"
     - Article 3: "5 ways to improve AI SaaS margins"
   - Distribute via: Hacker News, Reddit (r/SaaS, r/SideProject), Twitter

3. **Cold Outreach**
   - Target: 200 more AI SaaS companies
   - Source: Crunchbase, Product Hunt, LinkedIn
   - Template: Emphasize self-service, case studies, ROI

### Deliverables
- [ ] 20-30 customers
- [ ] $4K-9K MRR
- [ ] Self-service onboarding (<5 min)
- [ ] Product Hunt top 15

### Success Criteria
- 10+ customers from self-service (not manual outreach)
- <10% churn in first 3 months
- NPS > 40
- At least 1 customer says "I'd pay 5x for this"

### Go/No-Go Decision
**End of Week 12:** If <10 customers or <30 NPS, iterate on product-market fit

---

## Phase 3: Full Product (Weeks 13-24)

### Goal
Premium product with benchmarking at $399-599/mo, 50-100 customers

### What We Build

#### Peer Benchmarking Engine (Weeks 13-15)
**Objective:** Build anonymous peer benchmarking system

**Privacy-First Design:**
- Hash customer IDs (SHA-256) for anonymization
- Remove PII (customer names, emails)
- Aggregate only (minimum 10 customers for percentile)
- Opt-out option (customers can exclude themselves)

**Benchmark Metrics:**
- Margin percent (25th, 50th, 75th percentile)
- Cost per customer (by ARR band)
- Usage per model (GPT-4 vs. Claude)
- Cost per endpoint (chat vs. analysis)

**Database Schema:**
```sql
-- Benchmark data table (anonymized)
CREATE TABLE benchmark_data (
    id SERIAL PRIMARY KEY,
    customer_hash VARCHAR(255) NOT NULL UNIQUE,
    arr_band VARCHAR(50) NOT NULL,
    margin_percent DECIMAL(5, 2) NOT NULL,
    cost_per_customer DECIMAL(10, 2) NOT NULL,
    model_distribution JSONB NOT NULL,
    endpoint_distribution JSONB NOT NULL,
    opted_out BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Benchmark percentiles table (pre-calculated)
CREATE TABLE benchmark_percentiles (
    id SERIAL PRIMARY KEY,
    arr_band VARCHAR(50) NOT NULL,
    metric VARCHAR(100) NOT NULL,
    percentile_25 DECIMAL(10, 2) NOT NULL,
    percentile_50 DECIMAL(10, 2) NOT NULL,
    percentile_75 DECIMAL(10, 2) NOT NULL,
    sample_size INTEGER NOT NULL,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_benchmark_percentiles_band_metric ON benchmark_percentiles(arr_band, metric);
```

**Benchmark Calculation Logic:**
```python
# Anonymize and store customer data
def anonymize_customer_data(customer_id):
    # Fetch customer metrics
    margin = db.query_one("""
        SELECT margin_percent, revenue
        FROM margin_reports
        WHERE customer_id = %s
        ORDER BY report_date DESC
        LIMIT 1
    """, (customer_id,))

    if not margin:
        return

    # Calculate ARR band
    arr = margin.revenue * 12
    if arr < 100000:
        arr_band = '<$100K'
    elif arr < 500000:
        arr_band = '$100K-$500K'
    elif arr < 1000000:
        arr_band = '$500K-$1M'
    else:
        arr_band = '>$1M'

    # Calculate cost per customer
    customer_count = db.query_one("""
        SELECT COUNT(DISTINCT customer_id)
        FROM customer_costs
        WHERE stripe_customer_id = %s
    """, (customer_id,)).count

    cost_per_customer = margin.revenue / customer_count if customer_count > 0 else 0

    # Fetch model distribution
    model_distribution = db.query_one("""
        SELECT costs_by_model
        FROM customer_costs
        WHERE stripe_customer_id = %s
        ORDER BY cost_date DESC
        LIMIT 1
    """, (customer_id,)).costs_by_model

    # Fetch endpoint distribution
    endpoint_distribution = db.query_one("""
        SELECT costs_by_endpoint
        FROM customer_costs
        WHERE stripe_customer_id = %s
        ORDER BY cost_date DESC
        LIMIT 1
    """, (customer_id,)).costs_by_endpoint

    # Hash customer ID
    customer_hash = hashlib.sha256(customer_id.encode()).hexdigest()

    # Store or update benchmark data
    db.insert_or_update('benchmark_data', {
        'customer_hash': customer_hash,
        'arr_band': arr_band,
        'margin_percent': margin.margin_percent,
        'cost_per_customer': cost_per_customer,
        'model_distribution': json.dumps(model_distribution),
        'endpoint_distribution': json.dumps(endpoint_distribution)
    })

# Calculate percentiles
def calculate_percentiles():
    arr_bands = ['<$100K', '$100K-$500K', '$500K-$1M', '>$1M']
    metrics = ['margin_percent', 'cost_per_customer']

    for arr_band in arr_bands:
        for metric in metrics:
            # Fetch all values for this ARR band (opted-in only)
            values = db.query("""
                SELECT {metric}
                FROM benchmark_data
                WHERE arr_band = %s AND opted_out = FALSE
            """.format(metric=metric), (arr_band,))

            values = [v[0] for v in values if v[0] is not None]

            if len(values) < 10:
                continue  # Not enough data

            # Calculate percentiles
            p25 = np.percentile(values, 25)
            p50 = np.percentile(values, 50)
            p75 = np.percentile(values, 75)

            # Store percentiles
            db.insert_or_update('benchmark_percentiles', {
                'arr_band': arr_band,
                'metric': metric,
                'percentile_25': p25,
                'percentile_50': p50,
                'percentile_75': p75,
                'sample_size': len(values)
            })
```

**API Endpoint:**
```
GET /analytics/benchmarks/{id}

Response:
{
  "customer_id": "cus_123",
  "arr_band": "$100K-$500K",
  "benchmarks": {
    "margin_percent": {
      "customer_value": 45.2,
      "percentile_25": 35.0,
      "percentile_50": 42.0,
      "percentile_75": 55.0,
      "customer_percentile": 65
    },
    "cost_per_customer": {
      "customer_value": 120.50,
      "percentile_25": 80.0,
      "percentile_50": 110.0,
      "percentile_75": 150.0,
      "customer_percentile": 55
    }
  },
  "sample_size": 127,
  "last_updated": "2026-01-15"
}
```

**Privacy Policy:**
- Data anonymization process documented
- Minimum 10 companies for percentile
- Opt-out option (one-click)
- Data retention policy (90 days)

**Deliverables:**
- Benchmark calculation scripts
- Database migrations
- API endpoint
- Privacy policy documentation
- Opt-out flow in dashboard

#### Pricing Optimization Recommendations (Weeks 16-17)
**Objective:** Build pricing recommendation engine

**Features:**
- Analyze customer cost vs. revenue
- Identify underpriced customers (margin < 20%)
- Suggest pricing tiers based on cost bands
- ROI calculator: "Raise price by $X, improves margin by Y%"

**Recommendation Logic:**
```python
def generate_pricing_recommendations(customer_id):
    # Fetch customer metrics
    cost = db.query_one("""
        SELECT total_cost, costs_by_model, costs_by_endpoint
        FROM customer_costs
        WHERE customer_id = %s
        ORDER BY cost_date DESC
        LIMIT 1
    """, (customer_id,))

    revenue = db.query_one("""
        SELECT revenue
        FROM margin_reports
        WHERE customer_id = %s
        ORDER BY report_date DESC
        LIMIT 1
    """, (customer_id,))

    margin_percent = ((revenue.revenue - cost.total_cost) / revenue.revenue) * 100

    recommendations = []

    # Recommendation 1: Underpriced customers
    if margin_percent < 20:
        # Calculate price increase needed to reach 40% margin
        target_margin = 40
        target_revenue = cost.total_cost / (1 - target_margin / 100)
        price_increase = target_revenue - revenue.revenue

        recommendations.append({
            'type': 'PRICE_INCREASE',
            'priority': 'HIGH',
            'title': 'Increase price to improve margins',
            'description': f"Your margin is {margin_percent:.1f}%. Increasing price by ${price_increase:.2f}/mo would improve margin to 40%.",
            'current_price': revenue.revenue,
            'recommended_price': target_revenue,
            'price_increase': price_increase,
            'current_margin': margin_percent,
            'projected_margin': target_margin
        })

    # Recommendation 2: Tiered pricing based on usage
    if cost.costs_by_endpoint:
        # Group customers by usage (low, medium, high)
        usage_tiers = {
            'low': (0, cost.total_cost * 0.5),
            'medium': (cost.total_cost * 0.5, cost.total_cost * 1.5),
            'high': (cost.total_cost * 1.5, float('inf'))
        }

        pricing_tiers = []
        for tier_name, (min_cost, max_cost) in usage_tiers.items():
            # Calculate price for this tier (40% margin target)
            avg_cost = (min_cost + max_cost) / 2
            price = avg_cost / (1 - 40 / 100)

            pricing_tiers.append({
                'tier': tier_name.title(),
                'usage_range': f"${min_cost:.0f}-${max_cost:.0f}",
                'recommended_price': round(price, 2)
            })

        recommendations.append({
            'type': 'TIERED_PRICING',
            'priority': 'MEDIUM',
            'title': 'Introduce tiered pricing',
            'description': 'Offer 3 tiers based on usage to capture more value from high-usage customers.',
            'tiers': pricing_tiers
        })

    # Recommendation 3: Cost optimization
    if cost.costs_by_model:
        # Find most expensive model
        most_expensive_model = max(cost.costs_by_model.items(), key=lambda x: x[1])

        recommendations.append({
            'type': 'COST_OPTIMIZATION',
            'priority': 'LOW',
            'title': 'Optimize model usage',
            'description': f"{most_expensive_model[0]} accounts for ${most_expensive_model[1]:.2f} ({most_expensive_model[1]/cost.total_cost*100:.1f}%) of costs. Consider caching or cheaper alternatives for non-critical requests.",
            'model': most_expensive_model[0],
            'cost': most_expensive_model[1],
            'percent_of_total': most_expensive_model[1] / cost.total_cost * 100
        })

    return recommendations
```

**ROI Calculator:**
```python
def calculate_roi(customer_id, price_increase):
    # Fetch current metrics
    current_revenue = db.query_one("SELECT revenue FROM margin_reports WHERE customer_id = %s", (customer_id,)).revenue
    current_cost = db.query_one("SELECT total_cost FROM customer_costs WHERE customer_id = %s", (customer_id,)).total_cost

    # Calculate new metrics
    new_revenue = current_revenue + price_increase
    new_margin = ((new_revenue - current_cost) / new_revenue) * 100
    margin_improvement = new_margin - ((current_revenue - current_cost) / current_revenue * 100)

    # Calculate annualized impact
    annual_increase = price_increase * 12

    return {
        'price_increase': price_increase,
        'new_revenue': new_revenue,
        'new_margin': new_margin,
        'margin_improvement': margin_improvement,
        'annualized_increase': annual_increase
    }
```

**Deliverables:**
- Pricing recommendation engine
- ROI calculator
- UI components for displaying recommendations
- Unit tests (30+ test cases)

#### Advanced Analytics (Weeks 18-19)
**Objective:** Build advanced analytics features

**Feature 1: Cohort Analysis**
- Group customers by cohort (signup month, ARR band, industry)
- Calculate margin by cohort over time
- Identify high-value cohorts

**Feature 2: Forecasting**
- Predict next month's costs based on usage trends
- Linear regression or simple moving average
- Display forecasted margin

**Feature 3: Trend Detection**
- Detect margin compression over time
- Alert if margin declines for 3+ consecutive months
- Identify customers with declining margins

**Feature 4: What-If Analysis**
- Model impact of price changes
- Model impact of cost optimizations
- Model impact of churn reduction

**Cohort Analysis Logic:**
```python
def cohort_analysis():
    # Group customers by signup month
    cohorts = db.query("""
        SELECT
            DATE_TRUNC('month', MIN(created_at)) as cohort_month,
            customer_id,
            COUNT(DISTINCT id) as customer_count
        FROM stripe_customers
        GROUP BY cohort_month, customer_id
        ORDER BY cohort_month
    """)

    cohort_data = []
    for cohort in cohorts:
        # Calculate margin for this cohort over time
        margin_over_time = db.query("""
            SELECT
                DATE_TRUNC('month', report_date) as month,
                AVG(margin_percent) as avg_margin
            FROM margin_reports
            WHERE customer_id = %s
            GROUP BY month
            ORDER BY month
        """, (cohort.customer_id,))

        cohort_data.append({
            'cohort_month': cohort.cohort_month,
            'customer_count': cohort.customer_count,
            'margin_over_time': margin_over_time
        })

    return cohort_data
```

**Forecasting Logic:**
```python
def forecast_costs(customer_id, periods=1):
    # Fetch last 90 days of costs
    costs = db.query("""
        SELECT cost_date, total_cost
        FROM customer_costs
        WHERE customer_id = %s
        AND cost_date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY cost_date
    """, (customer_id,))

    if len(costs) < 30:
        return None  # Not enough data

    # Simple moving average forecast
    window = 30
    forecast = []

    for i in range(periods):
        # Take last 30 days average
        recent_costs = [c.total_cost for c in costs[-window:]]
        avg_cost = sum(recent_costs) / len(recent_costs)

        forecast.append({
            'period': i + 1,
            'forecasted_cost': avg_cost,
            'forecast_date': datetime.now() + timedelta(days=30 * (i + 1))
        })

        # Add forecast to costs for next iteration
        costs.append({'cost_date': forecast[-1]['forecast_date'], 'total_cost': avg_cost})

    return forecast
```

**Deliverables:**
- Cohort analysis module
- Forecasting module
- Trend detection module
- What-if analysis module
- UI components for displaying analytics

#### PDF Export (Week 20)
**Objective:** Generate PDF reports for CFO reviews

**Report Sections:**
1. **Executive Summary**
   - Total customers
   - Average margin %
   - Unprofitable customer count
   - Month-over-month trends

2. **Customer P&L**
   - Top 10 customers by revenue
   - Top 10 unprofitable customers
   - Margin trends

3. **Cost Breakdown**
   - Costs by model
   - Costs by endpoint
   - Cost trends

4. **Benchmark Comparison**
   - How customer compares to peers
   - Percentile ranks
   - Gap analysis

5. **Recommendations**
   - Pricing optimization
   - Cost optimization
   - Action items

**PDF Generation:**
```python
def generate_pdf_report(customer_id, start_date, end_date):
    # Fetch data
    margin_report = fetch_margin_report(customer_id, start_date, end_date)
    cost_breakdown = fetch_cost_breakdown(customer_id, start_date, end_date)
    benchmarks = fetch_benchmarks(customer_id)
    recommendations = generate_pricing_recommendations(customer_id)

    # Generate PDF
    pdf = PDFGenerator()

    # Executive Summary
    pdf.add_section("Executive Summary", """
        Total Customers: {customer_count}
        Average Margin: {avg_margin}%
        Unprofitable Customers: {unprofitable_count}
        Revenue: ${total_revenue:,.2f}
        Cost: ${total_cost:,.2f}
    """.format(
        customer_count=margin_report['customer_count'],
        avg_margin=margin_report['avg_margin'],
        unprofitable_count=margin_report['unprofitable_count'],
        total_revenue=margin_report['total_revenue'],
        total_cost=margin_report['total_cost']
    ))

    # Customer P&L
    pdf.add_section("Customer Profit & Loss", generate_customer_p_l_table(margin_report))

    # Cost Breakdown
    pdf.add_section("Cost Breakdown by Model", generate_cost_breakdown_chart(cost_breakdown))

    # Benchmarks
    pdf.add_section("Benchmark Comparison", generate_benchmark_comparison(benchmarks))

    # Recommendations
    pdf.add_section("Recommendations", generate_recommendations_table(recommendations))

    # Save PDF
    filename = f"margin_report_{customer_id}_{end_date}.pdf"
    pdf.save(filename)

    return filename
```

**Email Delivery:**
```python
def email_monthly_report(customer_id):
    # Generate PDF
    filename = generate_pdf_report(customer_id, last_month_start, last_month_end)

    # Send email
    send_email(
        to=f"cfo@{customer_id}.com",
        subject="Monthly Margin Report",
        body="Please find attached your monthly margin report.",
        attachments=[filename]
    )
```

**Deliverables:**
- PDF generation module
- Email automation
- Report templates
- On-demand PDF generation (UI button)

#### Admin Dashboard (Weeks 21-22)
**Objective:** Build multi-customer admin dashboard

**Features:**
1. **Multi-Customer View**
   - All customers in one table
   - Sort, filter, search
   - Export to CSV/JSON

2. **Benchmark Trends**
   - How percentile ranks change over time
   - Aggregate metrics across all customers
   - Benchmark growth (sample size over time)

3. **Alert Management**
   - Configure alerts across customers
   - Bulk alert settings
   - Alert performance metrics

4. **Data Export**
   - CSV export
   - JSON export
   - API access for further analysis

**Admin Pages:**
- **Page 1:** Customer Overview (all customers)
- **Page 2:** Benchmark Trends (percentile changes)
- **Page 3:** Alert Configuration (bulk settings)
- **Page 4:** Data Export (CSV, JSON)

**Deliverables:**
- Admin dashboard UI
- Bulk alert configuration
- Data export functionality
- Admin authentication (role-based access)

### What We Sell

**Pricing Tiers:**

| Plan | Price | Customers | Features | Alerts | Benchmarking | PDF Reports |
|------|-------|-----------|----------|--------|--------------|-------------|
| **Starter** | $199/mo | Up to 50 | Cost aggregation, margin calculation, basic dashboard | Email only | ❌ | ❌ |
| **Pro** | $299/mo | Unlimited | All Starter + customer detail, trends | Slack + Email | ❌ | ❌ |
| **Growth** | $399/mo | Unlimited | All Pro + pricing recommendations, advanced analytics | Slack + Email | ✅ | ❌ |
| **Enterprise** | $599/mo | Unlimited | All Growth + custom insights, priority support | Slack + Email + SMS | ✅ (custom) | ✅ (monthly) |

**Launch Strategy:**

1. **Enterprise Tier Launch (Week 23)**
   - Case studies: "We saved $50K/month by fixing unprofitable segment"
   - Target: AI SaaS with $100K+/mo LLM spend
   - Features: Custom pricing insights, priority support, PDF reports

2. **Partnerships**
   - **Helicone:** Complementary product (they track requests, we analyze margins)
   - **Langfuse:** Complementary product (they debug apps, we optimize economics)
   - **Stripe Partner Program:** Distribution to AI SaaS companies

3. **Outbound Sales**
   - Target: AI SaaS with $100K+/mo LLM spend
   - Source: Crunchbase (Series B+), LinkedIn (VP Finance)
   - Offer: "We'll find $50K+ in margin improvements"

**Expansion Channels:**

1. **VC Partnerships**
   - Y Combinator (portfolio companies)
   - Sequoia (AI portfolio)
   - a16z (AI investments)
   - Offer: Free pilot for portfolio companies

2. **Distribution Partnerships**
   - Stripe Partner Program
   - Helicone Marketplace
   - Langfuse Integrations

3. **Content Marketing**
   - "AI SaaS Unit Economics" whitepaper
   - "How to Price AI Products" guide
   - "Margin Optimization Playbook" PDF

### Deliverables
- [ ] 50-100 customers
- [ ] $20K-60K MRR ($240K-720K ARR run rate)
- [ ] 50+ companies in benchmarking dataset
- [ ] 3-5 partnerships

### Success Criteria
- 50+ paying customers
- $20K+ MRR
- Benchmarking moat: 50+ companies
- Acquisition through partnerships (not just outbound)

### Go/No-Go Decision
**End of Week 24:** If <30 customers or <$10K MRR, consider pivot or acquisition

---

## Implementation Timeline

| Phase | Duration | Team | Customers | MRR | Key Milestones |
|-------|----------|------|-----------|-----|----------------|
| **Phase 1** | 4 weeks | Solo founder | 5-10 | $500-1K | First customer, validate demand |
| **Phase 2** | 8 weeks | +1 contractor | 20-30 | $4K-9K | Self-service, Product Hunt |
| **Phase 3** | 12 weeks | +2 engineers | 50-100 | $20K-60K | Benchmarking, partnerships |

**Total:** 24 weeks to full product

**Team Expansion:**
- **Phase 1:** Solo founder (all roles)
- **Phase 2:** +1 contractor (frontend developer)
- **Phase 3:** +2 engineers (full-stack, data engineer)

**Hiring Timeline:**
- **Week 5:** Hire frontend contractor (Weeks 5-12)
- **Week 13:** Hire full-stack engineer (Weeks 13-24)
- **Week 17:** Hire data engineer (Weeks 17-24)

---

## Critical Dependencies

### Metering Service (Already Built)
✅ **Completed Infrastructure:**
- Stripe v2 integration (1,500+ lines of code)
- Multi-tenant database (30+ tables)
- Security (HMAC webhook verification, JWT auth, RLS)
- CostService (1,600+ lines, multi-provider pricing)
- Testing (50+ test files)
- Deployment guides (INFRASTRUCTURE.md)
- API specification (13 endpoints documented)

### What We Need to Build

**Phase 1 (Concierge MVP):**
- ✅ Manual SQL queries (leveraging metering service database)
- ✅ Python scripts for cost aggregation
- ✅ Google Sheets dashboard (manual setup)
- ✅ Email automation (SMTP)

**Phase 2 (Automated MVP):**
- ⏳ Analytics API (3 endpoints)
- ⏳ Margin calculation engine (batch jobs)
- ⏳ Anomaly detection service
- ⏳ Alerting system (Slack/email)
- ⏳ Basic dashboard UI (3 pages)

**Phase 3 (Full Product):**
- ⏳ Benchmarking engine (percentile calculations)
- ⏳ Pricing optimization recommendations
- ⏳ Advanced analytics (cohort, forecasting, what-if)
- ⏳ PDF export
- ⏳ Admin dashboard

### External Dependencies

**Stripe API:**
- Customer data
- Subscription data
- Invoice data
- Pricing data

**Metering Service API:**
- Meter events
- Cost data
- Usage data

**Third-Party Services:**
- Slack (webhooks for alerts)
- SendGrid (email delivery)
- Twilio (SMS alerts, optional)
- AWS/GCP (hosting)

---

## Risk Mitigation

### Technical Risks

**Risk: Stripe API rate limits**
- **Impact:** Can't fetch revenue data for all customers
- **Probability:** Medium (high customer count)
- **Mitigation:**
  - Cache revenue data (refresh daily)
  - Batch API calls (fetch 100 customers at a time)
  - Use Stripe Connect (OAuth, higher rate limits)
  - Implement exponential backoff

**Risk: Large aggregation queries slow**
- **Impact:** Dashboard loading times >10 seconds
- **Probability:** High (1000+ customers, millions of meter events)
- **Mitigation:**
  - Pre-aggregate daily (batch jobs)
  - Use database indexes (customer_id, date)
  - Consider ClickHouse for analytics (faster than PostgreSQL)
  - Implement caching (Redis)
  - Pagination (50 customers per page)

**Risk: Anomaly detection false positives**
- **Impact:** Customers ignore alerts, alert fatigue
- **Probability:** Medium (statistical anomalies aren't always business issues)
- **Mitigation:**
  - Require 2+ standard deviations (not just 1)
  - Require minimum threshold (20% deviation)
  - Allow customers to tune thresholds
  - Implement alert suppression (acknowledge repeated alerts)
  - Machine learning model (learn from customer feedback)

**Risk: Benchmarking data privacy concerns**
- **Impact:** Customers opt-out, small sample size
- **Probability:** Medium (customers may be sensitive)
- **Mitigation:**
  - Transparent privacy policy (document anonymization)
  - Opt-out option (one-click)
  - Minimum 10 companies for percentile
  - Hash customer IDs (SHA-256)
  - Remove PII (names, emails)
  - Third-party audit (optional)

### Market Risks

**Risk: Can't get first 5 customers**
- **Impact:** Can't validate demand, pivot or shutdown
- **Probability:** Low (strong value proposition)
- **Mitigation:**
  - Lower price to $49/mo (if needed)
  - Offer free trials (14 days)
  - Expand outreach (500 companies instead of 200)
  - Partner with YC/Sequoia (portfolio companies)
  - Cold call (not just email)

**Risk: High churn (>10% monthly)**
- **Impact:** Can't grow MRR, negative word-of-mouth
- **Probability:** Medium (competitive market)
- **Mitigation:**
  - Improve onboarding (reduce time-to-value)
  - Add features (requested by customers)
  - Reduce price (if too expensive)
  - Annual contracts (discount for 12-month commitment)
  - Customer success manager (check-in calls)

**Risk: Can't raise capital**
- **Impact:** Can't hire team, slow growth
- **Probability:** Low (strong traction in Phase 1)
- **Mitigation:**
  - Bootstrap longer (extend runway)
  - Hire contractors (not full-time)
  - Revenue-funded growth (reinvest profits)
  - Angel investors (smaller checks)

### Competitive Risks

**Risk: CloudZero launches AI cost product**
- **Impact:** Lose competitive differentiation
- **Probability:** Medium (they mention "AI Cost Optimization" on site)
- **Mitigation:**
  - Focus on CFO buyer (they focus on FinOps)
  - Customer-level P&L (unique feature)
  - Startups focus (they focus on enterprise)
  - Partnership (complementary, not competitive)
  - Move fast (establish brand before they launch)

**Risk: Helicone adds margin features**
- **Impact:** Lose customers to existing tool
- **Probability:** Low (technical focus, not financial)
- **Mitigation:**
  - Stripe integration (they'd need to build this)
  - Benchmarking (data moat)
  - CFO buyer (they sell to engineers)
  - Partnership (complementary products)

**Risk: Open-source competitor launches**
- **Impact:** Can't compete with free
- **Probability:** Low (complex to build)
- **Mitigation:**
  - Data moat (benchmarking dataset)
  - Switching costs (historical data)
  - Service (customer success, onboarding)
  - Enterprise features (SLAs, compliance)

---

## Success Metrics

### Phase 1 (Weeks 1-4)

**Financial Metrics:**
- [ ] 5+ paying customers
- [ ] $500-1,000 MRR
- [ ] <$1K CAC (customer acquisition cost)
- [ ] >10% conversion from outreach (5 customers from 50 emails)

**Product Metrics:**
- [ ] 3+ customers say "This is worth 10x what I'm paying"
- [ ] 2+ customers willing to provide case study
- [ ] <2 days time-to-first-report
- [ ] 0% churn (all customers renew month 2)

**Qualitative Metrics:**
- [ ] Validate demand (3+ customers by week 4)
- [ ] Identify top 3 feature requests
- [ ] Refine pricing ($99/mo validated)
- [ ] Understand ideal customer profile

### Phase 2 (Weeks 5-12)

**Financial Metrics:**
- [ ] 20+ paying customers
- [ ] $4K-9K MRR
- [ ] <$500 CAC
- [ ] <10% monthly churn
- [ ] >$100 ARPU (average revenue per user)

**Product Metrics:**
- [ ] <5 min self-service onboarding
- [ ] Product Hunt top 15 (150+ upvotes)
- [ ] 50% of customers from self-service (not manual outreach)
- [ ] <10% support requests (product is intuitive)

**Customer Satisfaction:**
- [ ] NPS > 40
- [ ] 1+ customer says "I'd pay 5x for this"
- [ ] <48 hours response time for support
- [ ] 90%+ customer satisfaction (surveys)

**Growth Metrics:**
- [ ] 20% month-over-month growth
- [ ] 50+ trial signups
- [ ] 30+% conversion from trial to paid
- [ ] 5+ case studies

### Phase 3 (Weeks 13-24)

**Financial Metrics:**
- [ ] 50+ paying customers
- [ ] $20K-60K MRR
- [ ] <$1K CAC
- [ ] <5% monthly churn
- [ ] >$400 ARPU

**Product Metrics:**
- [ ] 50+ companies in benchmarking dataset
- [ ] 30+% of customers on Growth/Enterprise tier
- [ ] 10+% month-over-month growth
- [ ] 3+ partnerships (Helicone, Langfuse, Stripe)

**Competitive Moat:**
- [ ] Benchmarking data moat (50+ companies)
- [ ] Switching costs (historical data, alert configs)
- [ ] Brand recognition (top 3 in AI SaaS analytics)
- [ ] Customer retention (90%+ renewal rate)

**Customer Satisfaction:**
- [ ] NPS > 50
- [ ] 80%+ of customers say "can't live without it"
- [ ] <24 hours response time for Enterprise customers
- [ ] 95%+ customer satisfaction

**Business Health:**
- [ ] Positive unit economics (LTV > 3x CAC)
- [ ] <12 month payback period
- [ ] 70%+ gross margin
- [ ] $240K-720K ARR run rate

---

## Next Steps

### Immediate (Week 1)

**Documentation:**
1. [ ] Create customer list (200 AI SaaS companies)
2. [ ] Write cold email template
3. [ ] Set up landing page (simple: value prop, email capture)
4. [ ] Create onboarding checklist (PDF)

**Infrastructure:**
1. [ ] Set up Google Sheets template
2. [ ] Write SQL queries for cost aggregation
3. [ ] Test Stripe CLI commands
4. [ ] Set up email automation (SMTP)

**Outreach:**
1. [ ] Verify customer list (validate they use Stripe, have LLM usage)
2. [ ] Find founder/CFO email addresses
3. [ ] Personalize cold emails (reference their product)
4. [ ] Set up email tracking (open rates, reply rates)

### This Week (Week 1)

**Day 1-2:**
1. [ ] Send 50 cold emails
2. [ ] Set up email automation (auto-responses)
3. [ ] Create sample report (anonymized data)

**Day 3-4:**
1. [ ] Follow up with non-responders
2. [ ] Book 5 discovery calls
3. [ ] Send sample report to interested prospects

**Day 5:**
1. [ ] Close first customer
2. [ ] Collect API keys (Stripe, Metering Service)
3. [ ] Run cost aggregation script

### This Month (Weeks 1-4)

**Week 1:**
- [ ] Send 200 cold emails
- [ ] Book 20 discovery calls
- [ ] Close 3 customers

**Week 2:**
- [ ] Deliver first reports (3 customers)
- [ ] Collect feedback
- [ ] Iterate on report format
- [ ] Close 2 more customers

**Week 3:**
- [ ] Deliver weekly reports (5 customers)
- [ ] Set up Google Sheets dashboards
- [ ] Collect testimonials
- [ ] Close 2 more customers

**Week 4:**
- [ ] Deliver weekly reports (7 customers)
- [ ] Collect case studies (2-3 customers)
- [ ] Analyze metrics (churn, satisfaction)
- [ ] Go/No-Go decision

**End of Month Deliverables:**
- [ ] 5-10 paying customers
- [ ] $500-1,000 MRR
- [ ] 3-5 case studies
- [ ] Validated demand
- [ ] Decision: Pivot or proceed to Phase 2

---

## Appendix

### A. Customer Discovery Questions

**Qualification Questions:**
1. How many customers do you have?
2. What's your monthly LLM spend?
3. Do you know which customers are profitable?
4. How do you track cost-to-serve per customer?
5. Would you pay $99/mo for weekly margin reports?

**Discovery Call Questions:**
1. What's your current process for calculating customer margins?
2. How long does it take to aggregate costs per customer?
3. Have you identified any unprofitable customers?
4. What would you do with customer-level margin data?
5. What's your budget for analytics tools?

**Feedback Questions (after first report):**
1. Was the report actionable?
2. What insights were most valuable?
3. What's missing from the report?
4. Would you pay 10x for this ($990/mo)?
5. Can we use your logo on our website?

### B. Cold Email Templates

**Template 1: Initial Outreach**
```
Subject: Which of your customers are profitable?

Hi [Name],

I'm building a tool for AI SaaS companies to calculate customer-level margins.

Most AI SaaS founders I talk to don't know which customers are profitable and which are bleeding margin.

I'll manually aggregate your meter events, match them to Stripe revenue, and send you a weekly report showing:
- Which customers are profitable (margin > 20%)
- Which customers are unprofitable (margin < 20%)
- Cost breakdown by model (GPT-4, Claude, etc.)

Intro pricing: $99/mo (locked for 12 months).
I'm onboarding 5-10 companies this month.

Want to see a sample report?

[Your Name]
```

**Template 2: Follow-up with Sample Report**
```
Subject: Re: Which of your customers are profitable?

Hi [Name],

Following up on my previous email.

Here's a sample report (anonymized):
[Link to sample report]

This company discovered that 30% of their customers are unprofitable.

We can have the same report for you within 48 hours.

Interested?

[Your Name]
```

**Template 3: Final Call-to-Action**
```
Subject: Last call about customer margins

Hi [Name],

I'm closing the cohort this Friday.

I have 2 spots left for intro pricing ($99/mo, locked for 12 months).

After this, pricing goes up to $199/mo.

Want to claim a spot?

[Your Name]
```

### C. Sample Report Format

**PDF Report Structure:**

**Page 1: Executive Summary**
- Total customers: 127
- Average margin: 42.3%
- Unprofitable customers: 38 (30%)
- Total revenue: $127,500
- Total cost: $73,575
- Total margin: $53,925 (42.3%)

**Page 2: Top 10 Customers by Revenue**
| Customer | Revenue | Cost | Margin % | Status |
|----------|---------|------|----------|--------|
| cus_123 | $5,000 | $2,500 | 50.0% | Profitable |
| cus_456 | $3,000 | $1,800 | 40.0% | Profitable |
| ... | ... | ... | ... | ... |

**Page 3: Unprofitable Customers**
| Customer | Revenue | Cost | Margin % | Action |
|----------|---------|------|----------|--------|
| cus_789 | $1,000 | $1,200 | -20.0% | Raise price |
| cus_101 | $800 | $950 | -18.8% | Raise price |
| ... | ... | ... | ... | ... |

**Page 4: Cost Breakdown by Model**
| Model | Cost | % of Total |
|-------|------|------------|
| gpt-4 | $45,000 | 61.2% |
| claude-3-opus | $20,000 | 27.2% |
| gpt-3.5-turbo | $8,575 | 11.6% |

**Page 5: Week-over-Week Trends**
- Margin: 40.1% → 42.3% (+2.2%)
- Revenue: $120K → $127.5K (+6.3%)
- Cost: $71.8K → $73.6K (+2.5%)

### D. Database Schema (Full)

**Metering Service Tables (Already Built):**
- `meter_events` (meter events from Stripe)
- `stripe_customers` (customer data)
- `stripe_subscriptions` (subscription data)
- `stripe_invoices` (invoice data)

**New Tables (Phase 1-2):**
```sql
-- Customer costs table
CREATE TABLE customer_costs (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    cost_date DATE NOT NULL,
    total_cost DECIMAL(10, 2) NOT NULL,
    costs_by_model JSONB NOT NULL,
    costs_by_endpoint JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, cost_date)
);

-- Margin reports table
CREATE TABLE margin_reports (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    report_date DATE NOT NULL,
    revenue DECIMAL(10, 2) NOT NULL,
    cost DECIMAL(10, 2) NOT NULL,
    margin DECIMAL(10, 2) NOT NULL,
    margin_percent DECIMAL(5, 2) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, report_date)
);

-- Baseline values table
CREATE TABLE baseline_values (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    baseline_date DATE NOT NULL,
    baseline_daily_cost DECIMAL(10, 2) NOT NULL,
    baseline_total_cost DECIMAL(10, 2) NOT NULL,
    calculation_window INTEGER NOT NULL DEFAULT 30,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, baseline_date)
);

-- Anomalies table
CREATE TABLE anomalies (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    anomaly_date TIMESTAMP NOT NULL,
    current_cost DECIMAL(10, 2) NOT NULL,
    baseline_cost DECIMAL(10, 2) NOT NULL,
    deviation_percent DECIMAL(5, 2) NOT NULL,
    z_score DECIMAL(5, 2) NOT NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alert configurations table
CREATE TABLE alert_configurations (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    threshold_value DECIMAL(10, 2) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    channels JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alert history table
CREATE TABLE alert_history (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    alert_date TIMESTAMP NOT NULL,
    message TEXT NOT NULL,
    channels JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**New Tables (Phase 3):**
```sql
-- Benchmark data table (anonymized)
CREATE TABLE benchmark_data (
    id SERIAL PRIMARY KEY,
    customer_hash VARCHAR(255) NOT NULL UNIQUE,
    arr_band VARCHAR(50) NOT NULL,
    margin_percent DECIMAL(5, 2) NOT NULL,
    cost_per_customer DECIMAL(10, 2) NOT NULL,
    model_distribution JSONB NOT NULL,
    endpoint_distribution JSONB NOT NULL,
    opted_out BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Benchmark percentiles table (pre-calculated)
CREATE TABLE benchmark_percentiles (
    id SERIAL PRIMARY KEY,
    arr_band VARCHAR(50) NOT NULL,
    metric VARCHAR(100) NOT NULL,
    percentile_25 DECIMAL(10, 2) NOT NULL,
    percentile_50 DECIMAL(10, 2) NOT NULL,
    percentile_75 DECIMAL(10, 2) NOT NULL,
    sample_size INTEGER NOT NULL,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pricing recommendations table
CREATE TABLE pricing_recommendations (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    recommendation_date DATE NOT NULL,
    recommendation_type VARCHAR(100) NOT NULL,
    priority VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    data JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### E. API Specification (Full)

**Base URL:** `https://api.datafoundry.dev/analytics`

**Authentication:** Bearer token (Stripe Connect OAuth)

**Endpoints:**

**1. GET /analytics/customers/{id}/margins**
- Get margin data for a specific customer
- Parameters: `id` (customer ID), `start_date` (optional), `end_date` (optional)
- Response: Margin data (cost, revenue, margin percent, status)

**2. GET /analytics/customers/{id}/costs**
- Get cost breakdown for a specific customer
- Parameters: `id` (customer ID), `start_date` (optional), `end_date` (optional), `group_by` (optional)
- Response: Cost breakdown (by model, by endpoint, trends)

**3. GET /analytics/customers/{id}/revenue**
- Get revenue data for a specific customer
- Parameters: `id` (customer ID), `start_date` (optional), `end_date` (optional)
- Response: Revenue data (MRR, subscriptions, invoices)

**4. GET /analytics/benchmarks/{id}**
- Get benchmark data for a specific customer
- Parameters: `id` (customer ID)
- Response: Benchmark data (percentiles, customer rank, sample size)

**5. POST /analytics/reports/generate**
- Generate PDF report for a customer
- Parameters: `customer_id`, `start_date`, `end_date`
- Response: PDF file (download link)

**6. GET /analytics/anomalies**
- List recent anomalies
- Parameters: `customer_id` (optional), `severity` (optional), `acknowledged` (optional)
- Response: List of anomalies

**7. POST /analytics/anomalies/{id}/acknowledge**
- Acknowledge an anomaly
- Parameters: `id` (anomaly ID)
- Response: Success/failure

**8. GET /analytics/alerts/configurations**
- List alert configurations
- Parameters: `customer_id` (optional)
- Response: List of alert configurations

**9. POST /analytics/alerts/configurations**
- Create alert configuration
- Parameters: `customer_id`, `alert_type`, `threshold_value`, `channels`
- Response: Alert configuration

**10. PUT /analytics/alerts/configurations/{id}**
- Update alert configuration
- Parameters: `id` (configuration ID), `threshold_value`, `channels`, `enabled`
- Response: Updated configuration

### F. Competitive Intelligence Summary

**Key Findings:**
1. **White space exists** – No competitor offers customer-level margin analysis
2. **Pricing power exists** – $99-599/mo is competitive and justified
3. **Differentiation is clear** – Technical observability (competitors) vs. Business economics (you)
4. **Competitive threats are manageable** – CloudZero could expand, but enterprise focus creates opportunity
5. **Partnership opportunities** – Complement LLM observability tools

**Competitor Matrix:**

| Feature | Helicone | Langfuse | Braintrust | CloudZero | **Your Product** |
|---------|----------|----------|-----------|-----------|------------------|
| Customer-Level Costs | ❌ | ❌ | ❌ | ✅ (infrastructure) | ✅ (AI apps) |
| Margin Analysis | ❌ | ❌ | ❌ | ❌ | ✅ |
| Revenue Integration | ❌ | ❌ | ❌ | ❌ | ✅ (Stripe) |
| Anomaly Detection | ✅ (technical) | ✅ (technical) | ❌ | ✅ (spend) | ✅ (usage) |
| Alerting | ✅ | ✅ | ❌ | ✅ | ✅ |
| Benchmarking | ❌ | ❌ | ❌ | ❌ | ✅ (peer) |
| Pricing Starting At | $79/mo | Contact | $249/mo | Enterprise | $99-599/mo |
| Target Buyer | Engineering | Engineering | PM/Engineering | FinOps | CFO/VP Finance |

**Positioning Statement:**
"We're an AI unit economics platform. We help AI SaaS companies understand which customers are profitable, which are bleeding margin, and how to price for growth."

**Differentiation Strategy:**
- Don't say: "We're a billing platform" or "We're an observability tool"
- Say: "We calculate cost-to-serve per customer and identify unprofitable segments"

---

## Conclusion

This implementation roadmap outlines a 24-week journey from concierge MVP to full product, with clear go/no-go decision points at each phase.

**Key Success Factors:**
1. **Validate demand first** (Phase 1) before building automation
2. **Focus on CFO buyer** (not engineers) – unique positioning
3. **Build benchmarking moat** (data network effects)
4. **Competitive differentiation** (technical vs. business intelligence)

**Critical Path:**
- Week 1-4: Get 5-10 customers manually
- Week 5-12: Build self-service product
- Week 13-24: Add benchmarking and premium features

**Risk Mitigation:**
- Lower price if needed ($49/mo)
- Offer free trials (14 days)
- Partner with LLM observability tools
- Focus on startups (not enterprise)

**Next Steps:**
1. Create customer list (200 AI SaaS companies)
2. Send cold emails
3. Close first 5 customers
4. Deliver first reports

The competitive intelligence confirms that this product occupies a unique white space in the market. No competitor currently offers customer-level margin analysis for AI SaaS companies. By executing on this roadmap, we can establish first-mover advantage and build a data moat through benchmarking.

---

**Document Version:** 1.0
**Last Updated:** January 3, 2026
**Author:** Data Foundry Team
**Status:** Ready for Execution
