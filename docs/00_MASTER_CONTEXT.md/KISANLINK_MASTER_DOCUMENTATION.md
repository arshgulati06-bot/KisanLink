# KisanLink --- SIH 2026 Master Project Documentation

## Project

-   PS: **SIH26132 --- Strengthening market linkages and price discovery
    for farmers**
-   Organization: Government of Maharashtra
-   Category: Software
-   Theme: Agriculture, FoodTech & Rural Development
-   Product: **KisanLink**
-   Time available: **10 days**
-   Stack: HTML/CSS/JS + Python/Flask + MySQL + Python ML
-   Primary coding assistant: Antigravity
-   Primary architecture/mentoring: ChatGPT
-   Independent review: Claude

## 1. Problem

Farmers, especially smallholders and producer groups, may lack connected
visibility of current/expected prices, nearby markets, processors,
institutional buyers, digital channels, quality requirements, demand,
logistics, storage, payment reliability and buyer credentials. This can
cause quick selling, weak bargaining power and poor price realization.
Buyers can also struggle to aggregate consistent volumes and verify
quality.

### Core question

**Who should I sell to, where should I sell, when should I sell, what
effective price is better, and why?**

## 2. Official Expected Solution Areas

The PS expects a market-intelligence and transaction-enablement solution
covering: - mandi prices - buyer demand - quality requirements - arrival
volumes - transport options - storage options - localized price trends -
sale-window recommendations - farmer/FPO--verified-buyer matching - lot
creation - quality grading - digital offers - logistics coordination -
payment tracking - dispute/grievance processes

## 3. Product Vision

KisanLink is **Market Intelligence + Buyer Matching + Transaction
Enablement**.

It must not become merely a mandi-price dashboard, generic marketplace,
chatbot, CRUD app, or fake-AI demo.

The hero question is: \> **"What should this farmer do with this crop
right now, and why?"**

## 4. Why Two Dashboards?

The PS involves both supply and demand: - **Farmer/FPO dashboard:**
create crop lots and receive opportunities/offers. - **Buyer
dashboard:** create demand, view matching lots and make offers.

Without a buyer-side workflow, "buyer demand" and farmer-to-buyer
linkage cannot be demonstrated properly.

## 5. Farmer Flow

Login → Create Lot → Market Intelligence → Buyer Opportunities →
Recommendation → Receive Offer → Accept → Transaction Tracking.

Lot fields should be limited to useful data: - farmer/FPO - crop -
variety if needed - quantity - quality/grade - location -
harvest/availability date

## 6. Buyer Flow

Login → Create Demand → Matching Farmer Lots → Make Offer → Farmer
Accepts → Transaction Tracking.

Demand fields: - business name - crop - required quantity - required
quality - location - price/offer range - validity - verification status

## 7. Data Strategy

### Real external data

Use only verified sources, especially government/open mandi data such as
data.gov.in/AGMARKNET where the specific dataset is confirmed.

### Platform-generated data

Actual farmers and buyers can create their own records.

### Prototype seed data

Because buyer-demand data may not have a public dataset, use a small
clearly labelled seed/onboarded buyer dataset for the demo.

Never claim seed/demo buyers are real verified commercial buyers.

### Data categories

-   Market prices: government/open source, verify first.
-   Historical prices: same source if available.
-   Arrival volumes: source-dependent, verify.
-   Market list: government/open source, verify.
-   Buyer demand: platform onboarding + seed prototype data.
-   Farmer lots: user-generated.
-   Distance: mapping/geocoding/routing API, verify before dependency.
-   Transport: calculated estimate unless live data is verified.
-   Storage: onboarded/prototype facility data.
-   Payment: prototype status tracking.
-   Grievance: future/stub.

If a source/API cannot be verified: **"UNVERIFIED --- DO NOT BUILD A
DEPENDENT FEATURE YET."**

## 8. Data Feasibility --- First Priority

Before ML or final schema: 1. Download a real sample mandi dataset. 2.
Inspect columns. 3. Check Maharashtra coverage. 4. Check commodity
coverage. 5. Check history. 6. Check missing/duplicate data. 7. Check
names, dates and units. 8. Confirm access/usage conditions.

Do not invent database columns based on unavailable data.

## 9. Intelligence

### Buyer matching

For the 10-day MVP use an explainable weighted scoring engine rather
than pretending to have enough historical transactions for ML.

Possible factors: - price - quantity fit - quality match - distance -
buyer trust/verification

Illustrative starting weights: - Price 35% - Quantity fit 20% - Quality
20% - Distance 15% - Trust 10%

These weights must be tested/tuned.

### Net realization

`Gross sale value - estimated transport - estimated storage - relevant costs`

Do not assume the highest gross price is always best.

### ML

Best genuine ML candidate: price trend/short-term sale-window support
using historical market prices.

If history is insufficient: **"Insufficient historical data for reliable
forecast."**

Never fabricate forecasts.

## 10. Hero Feature --- Explainable Recommendation

Example: **Recommended Buyer: ABC Foods** - Offer: ₹27/kg - Quantity
match: Yes - Quality match: Yes - Distance: 32 km - Estimated transport:
₹800 - Trust status: Platform-Reviewed - Estimated net realization:
₹26,200

Then: **WHY THIS RECOMMENDATION?** - better effective offer - quantity
matches - quality matches - reasonable distance - buyer trust status -
transport cost considered

## 11. MVP --- MUST BUILD

1.  Farmer dashboard
2.  Buyer dashboard
3.  Farmer lot creation
4.  Buyer demand creation
5.  Market-price intelligence
6.  Buyer matching
7.  Net-realization calculation
8.  Explainable recommendation
9.  Digital offer
10. Offer acceptance
11. Basic transaction status
12. Real market data where verified
13. Proper backend/API/database integration

### SHOULD BUILD

-   price trends
-   basic forecasting if data is sufficient
-   transport estimate
-   storage display
-   buyer verification UI
-   grievance stub

### FUTURE

-   real payment gateway
-   live logistics
-   government KYC/GST integration
-   advanced demand forecasting
-   large-scale FPO aggregation
-   deeper e-NAM integration
-   mobile app/notifications

## 12. Tech Stack

### Frontend

HTML, CSS, JavaScript, Chart.js

### Backend

Python, Flask, REST APIs

### Database

MySQL

### Data/ML

Python, Pandas, NumPy, scikit-learn

Keep the stack understandable for a second-year student.

## 13. Architecture

``` text
Frontend
   ↓
REST API
   ↓
Flask Backend
   ↓
Services / Business Logic
   ↓
MySQL

External/Data Sources
   ↓
Data Ingestion + Cleaning
   ↓
Database
   ↓
Analytics / ML
   ↓
Recommendation Service
   ↓
Backend
   ↓
Frontend
```

## 14. Core Database

Initial tables: - users - farmer_profiles - buyer_profiles -
commodities - markets - market_prices - market_arrivals -
buyer_demands - lots - offers - recommendations - transactions

Future/stub: - logistics - storage_facilities - payments - grievances

Do not create tables without a real feature.

## 15. API Groups

### Auth

`POST /api/auth/register` `POST /api/auth/login`

### Farmer

`GET /api/farmers/profile` `POST /api/lots` `GET /api/lots`

### Buyer

`GET /api/buyers` `POST /api/buyer-demands` `GET /api/buyer-demands`

### Market

`GET /api/markets` `GET /api/prices` `GET /api/prices/trends`

### Intelligence

`POST /api/matching` `POST /api/recommendations`

### Offers

`POST /api/offers` `GET /api/offers`

### Transactions

`GET /api/transactions`

Exact request/response contracts must be finalized before integration.

## 16. Repository

``` text
KisanLink/
├── frontend/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── controllers/
│   │   ├── services/
│   │   ├── repositories/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── middleware/
│   │   └── config/
│   └── tests/
├── ml/
│   ├── data/
│   ├── preprocessing/
│   ├── training/
│   ├── evaluation/
│   └── inference/
├── database/
├── data/
├── docs/
└── README.md
```

## 17. Team

### You --- Team Lead + Integration

Architecture, final decisions, Antigravity coordination, GitHub,
integration, testing, SIH pitch/demo and project memory.

### Member 2 --- Frontend

Farmer dashboard, buyer dashboard, UI/UX, API integration.

### Member 3 --- Backend + Database

Flask, MySQL, authentication, APIs, business logic.

### Member 4 --- Data + ML

Data research, cleaning, ingestion, trends/forecasting, matching logic.

### Member 5 --- Testing + DevOps + Research

Testing, deployment, documentation, data-source verification,
presentation support.

All members may use Antigravity; each member owns their module.

## 18. GitHub

Use GitHub Desktop.

Flow:
`clone → branch → Antigravity work → commit → push → review → merge`

Branches: - main - frontend - backend - ml - testing-docs

Do not allow simultaneous uncontrolled AI rewrites of the same files.

## 19. Antigravity Rules

Before changing anything: 1. Read `docs/00_MASTER_CONTEXT.md`. 2.
Inspect existing code. 3. Read relevant architecture/API docs. 4.
Preserve working functionality. 5. Implement one module at a time. 6.
Test. 7. Report changed files and unresolved issues.

Do not generate the entire project in one giant operation.

## 20. Documentation Structure

``` text
docs/
├── 00_MASTER_CONTEXT.md
├── 01_PROBLEM_STATEMENT.md
├── 02_REQUIREMENTS.md
├── 03_USER_JOURNEYS.md
├── 04_SYSTEM_ARCHITECTURE.md
├── 05_DATABASE_DESIGN.md
├── 06_API_CONTRACT.md
├── 07_DATA_SOURCES.md
├── 08_DATA_PIPELINE.md
├── 09_ML_PLAN.md
├── 10_UI_UX_SPEC.md
├── 11_TEAM_ROLES.md
├── 12_DEVELOPMENT_PLAN.md
├── 13_TESTING.md
├── 14_DEPLOYMENT.md
└── 15_SIH_PITCH.md
```

`00_MASTER_CONTEXT.md` is the permanent handoff memory for ChatGPT,
Claude, Antigravity and the team. It must record current phase,
completed work, current work, next task, architecture, tech stack, data
sources, APIs, ML, known bugs and important decisions.

## 21. Ten-Day Plan

### Day 1

Data verification, architecture, DB, API contract, GitHub, docs.

### Day 2

MySQL schema, Flask foundation, authentication, frontend skeleton.

### Day 3

Farmer profile, buyer profile, lot, demand.

### Day 4

Market-data ingestion, price APIs, market UI.

### Day 5

Matching and net-realization.

### Day 6

Recommendation and "Why?" explanation.

### Day 7

Buyer dashboard and offers.

### Day 8

Transaction status, transport/storage display, price trends, ML if data
supports it.

### Day 9

Integration, testing, deployment, bug fixes.

### Day 10

Feature freeze, UI polish, documentation, PPT, demo rehearsal.

## 22. Critical End-to-End Demo

``` text
Farmer login
→ Create 1000 kg Tomato Grade A lot
→ Market intelligence
→ Buyer matching
→ Net realization
→ Best opportunity
→ Why recommendation?
→ Buyer offer
→ Farmer accepts
→ Transaction status
```

This flow must work reliably before adding extras.

## 23. What Must NOT Happen

-   No fake "real buyer" claims.
-   No unverified API dependencies.
-   No unnecessary ML.
-   No giant unfinished feature list.
-   No frontend disconnected from backend.
-   No last-day integration.
-   No AI rewriting working modules randomly.
-   No calling demo data real data.
-   No claiming a feature works without testing.

## 24. TODAY --- EXACT ACTIONS

1.  Create the GitHub repository.
2.  Create `docs/` and this master context.
3.  Assign team roles.
4.  Data member verifies the actual mandi dataset.
5.  Backend member prepares the DB schema.
6.  Frontend member prepares Farmer + Buyer wireframes.
7.  You coordinate architecture and ensure decisions are documented.
8.  Do not start feature-heavy coding until data feasibility is
    confirmed.

## 25. Final Product Positioning

**KisanLink is an explainable market-intelligence and
transaction-enablement platform that helps farmers discover better
selling opportunities and connect with suitable buyers.**

The differentiating question is:

> **"What should this farmer do with this crop right now, and why?"**

## 26. AI Handoff Instruction

When this project is opened in another AI tool:

> Read `docs/00_MASTER_CONTEXT.md` before making any change. This is
> SIH2026 project KisanLink for PS SIH26132. Do not restart the project,
> invent data/APIs, change architecture without discussion, or rewrite
> working modules. Inspect the existing code and documentation first.
> Complete features end-to-end and test them before moving on.


# 36. PS LINE-BY-LINE COVERAGE AUDIT — IMPORTANT

This section is the final audit against the exact SIH26132 problem description and expected outcome supplied by the team.

## A. Problem Description Coverage

### 1. Current prices
**Must cover.**
KisanLink must show current market/mandi price information for the selected commodity and relevant markets.

### 2. Expected prices
**Must cover, but carefully.**
This should be represented through price trend/forecasting or an expected-price indicator when enough historical data exists.
Never fabricate an expected price.

### 3. Nearby markets
**Must cover.**
The system should compare relevant nearby markets using farmer location and market location.

### 4. Processors
**Must cover.**
Processors are explicitly mentioned in the PS as possible market channels.
They should be represented as a buyer type/category in buyer profiles/demands.

### 5. Institutional buyers
**Must cover.**
Institutional buyers should also be represented as a buyer type/category.

### 6. Digital trading channels
**Must be acknowledged.**
For the 10-day prototype, a full external digital-trading integration is not required unless a verified API is available.
Our digital offer/transaction workflow demonstrates the platform-side digital linkage.
External channel integration can be future scope.

### 7. Quality specifications
**Must cover.**
Farmer lots need a quality/grade field and buyer demands need quality requirements.
The matching engine must consider quality compatibility.

### 8. Buyer demand
**Must cover.**
Buyer demand is a core input to matching.
Buyer dashboard/demand creation exists for this reason.

### 9. Logistics
**Must cover at least as an estimate/stub.**
The recommendation should consider distance and estimated transport cost where possible.
Full live logistics coordination can remain future scope.

### 10. Storage
**Must cover at least at decision-support level.**
Storage availability/cost should be represented where data is available.
This is important because the PS explicitly links storage constraints to forced selling.
A prototype storage module/display is preferable to ignoring storage completely.

### 11. Payment reliability
**Must cover.**
This is more than payment status.
Buyer trust/reliability should be a factor in the recommendation where data is available.
For the prototype, use a clearly labelled platform trust status rather than claiming external financial verification.

### 12. Buyer credentials
**Must cover.**
Buyer profiles should include credentials/verification information and a visible trust status.
Do not claim government KYC/GST verification unless actually implemented.

### 13. Weak bargaining power
**Product implication.**
The comparison/recommendation system should give the farmer multiple options rather than presenting a single unexplained buyer.
This supports transparent price discovery and better bargaining position.

### 14. Buyer aggregation problem
**Must cover.**
Buyer demand should include required quantity.
Farmer lots should include available quantity.
Matching should explicitly consider quantity fit.
FPO aggregation should be represented in the architecture, even if advanced multi-lot aggregation is future scope.

### 15. Consistent volumes
**Must cover conceptually.**
Buyer demand can specify a required quantity.
For FPO/aggregation, multiple farmer lots can eventually be grouped toward a buyer requirement.
In the 10-day prototype, implement a simple aggregation-ready data model rather than a complex auction/aggregation system.

### 16. Verify quality
**Must cover.**
The lot has a quality grade and the buyer demand has a required grade/specification.
The prototype can use a simple self-declared A/B/C grade.
Advanced computer-vision grading is not required by the PS and should not be invented.

---

# 37. EXPECTED OUTCOME — LINE-BY-LINE COVERAGE

## Improved farmer price realization
**Core KPI.**
Show estimated net realization and compare alternatives.

## Reduced information asymmetry
**Core KPI/story.**
Bring price, buyer demand, quality, logistics, storage and trust information together in one view.

## Lower transaction cost
**Should be demonstrated conceptually.**
Show distance/transport estimate and digital offer workflow.
Do not claim measured savings without real-world evidence.

## Stronger FPO aggregation
**Architecture requirement.**
Support `farmer/FPO` as a seller type.
A full multi-farmer aggregation workflow is future scope unless time allows.

## Reduced post-harvest loss
**Must be addressed in product logic/story.**
Storage availability and a sale-window recommendation are relevant because they help reduce forced/late selling and potentially avoid unnecessary holding.
Do not claim quantified loss reduction without field data.

## More reliable buyer sourcing
**Core feature.**
Buyer demand + trust/verification status + matching.

## Transparent transaction records
**Core feature.**
Offer and transaction status must be stored in the database with timestamps/status history where feasible.

---

# 38. USER TYPES — FINAL

The system should model these roles/types:

### 1. Farmer
Creates crop lots and evaluates selling opportunities.

### 2. FPO / Producer Group
Can represent aggregated supply and buyer requirements.
For the 10-day prototype, FPO can use the same lot/demand architecture with a seller-type flag rather than a completely separate application.

### 3. Buyer
A general buyer profile.

Buyer categories should include:
- Processor
- Institutional Buyer
- Aggregator
- Other eligible buyer

### 4. Admin / Platform Reviewer
Handles:
- buyer trust status
- prototype verification
- moderation
- seed-data management
- grievance status

Admin is an internal/support dashboard, not a primary hero dashboard.

---

# 39. MARKET CHANNEL MODEL

Do not model the system as “mandi vs buyer” only.

A farmer may have several selling channels:

```text
             SELLING OPPORTUNITIES
                     |
        +------------+------------+
        |            |            |
      MANDI       PROCESSOR   INSTITUTIONAL
        |            |            |
        +------------+------------+
                     |
              DIGITAL CHANNEL
```

KisanLink should normalize these opportunities so the farmer can compare them using a common decision view.

---

# 40. ARRIVAL VOLUME — DO NOT FORGET THIS

The PS explicitly mentions **arrival volumes**.

If the verified market dataset contains arrivals, store and use them.

Potential UI:

```text
Market: X
Current Modal Price: ₹...
Arrival Volume: ...
Price Trend: ↑
```

Possible intelligence:
- high arrivals may indicate supply pressure
- unusual arrival changes can be shown as context

Do NOT make causal claims such as “high arrivals always mean price will fall” without evidence.

If arrival data is unavailable for a selected source, mark it unavailable rather than inventing it.

---

# 41. SALE-WINDOW RECOMMENDATION

The PS explicitly asks for **sale-window recommendations**.

Therefore our recommendation should not only answer:

> “Which buyer?”

It should also answer:

> “Sell now / consider waiting / monitor.”

This is subject to data availability.

Possible result:

```text
SELLING WINDOW

Recommendation: SELL NOW
Reason:
- Current offer is strong
- Market trend is not strongly rising
- Suitable buyer demand is active
- Storage cost would reduce the benefit of waiting

Confidence: Medium
```

If the forecast is weak:
`Insufficient data for reliable timing recommendation.`

---

# 42. PRICE DISCOVERY SHOULD BE COMPARATIVE

The product should not show one price and call it price discovery.

Price discovery means the farmer can compare:

```text
Market A
Market B
Processor C
Institutional Buyer D
Buyer E
```

using relevant:
- price
- quantity
- quality
- distance
- transport
- storage
- trust

The system should preserve the raw/source price and the calculated effective/net realization separately.

---

# 43. RAW PRICE VS EFFECTIVE PRICE

Store/display both:

### Raw market/buyer price
The price obtained from the source or offer.

### Estimated effective/net realization
The amount after estimated costs.

This prevents misleading the farmer.

Example:

```text
Buyer A:
Gross = ₹28/kg
Transport = ₹2/kg
Net ≈ ₹26/kg

Buyer B:
Gross = ₹27/kg
Transport = ₹0.50/kg
Net ≈ ₹26.50/kg

Recommendation:
Buyer B
```

This is a strong demonstration of actual decision support.

---

# 44. TRANSACTION RECORDS

The PS explicitly asks for transparent transaction records.

Minimum status model:

```text
OFFERED
  ↓
ACCEPTED
  ↓
LOGISTICS_PENDING
  ↓
DELIVERED
  ↓
PAYMENT_PENDING
  ↓
PAID
  ↓
COMPLETED
```

Each state should have a timestamp where feasible.

Do not integrate a real payment gateway in the 10-day prototype unless it is already available and stable.

---

# 45. GRIEVANCE / DISPUTE

The PS explicitly mentions dispute/grievance processes.

Do NOT remove it entirely.

10-day MVP:
- grievance creation form
- transaction reference
- issue category
- description
- status: OPEN / UNDER_REVIEW / RESOLVED

Admin can update status.

This is a small feature but demonstrates that the expected outcome was read completely.

---

# 46. QUALITY GRADING — SCOPE CONTROL

The PS says “quality grading”.

For the 10-day prototype:
- self-declared Grade A/B/C
- buyer-required Grade A/B/C
- match/no-match

Optional future:
- commodity-specific grading rules
- image-based quality assessment
- lab/testing integration

Do not build computer vision unless it directly supports the selected commodity and there is enough time.

---

# 47. FPO AGGREGATION — SCOPE CONTROL

The PS explicitly mentions farmers/FPOs and stronger FPO aggregation.

Minimum architecture:

```text
Seller type:
FARMER / FPO

Seller
  ↓
Lot
  ↓
Buyer demand
```

Future:

```text
Multiple farmer lots
       ↓
FPO aggregation
       ↓
Combined lot
       ↓
Buyer demand
```

The 10-day MVP can remain aggregation-ready without implementing a complex cooperative-management system.

---

# 48. FINAL PS COVERAGE MATRIX

| PS concept | KisanLink treatment | Priority |
|---|---|---|
| Current prices | Market intelligence | MUST |
| Expected prices | Forecast/trend when data allows | SHOULD/MUST if reliable |
| Nearby markets | Location-based comparison | MUST |
| Processors | Buyer category | MUST |
| Institutional buyers | Buyer category | MUST |
| Digital trading channels | Digital offer workflow; external integration future | SHOULD |
| Quality specifications | Lot + buyer requirement | MUST |
| Buyer demand | Buyer dashboard | MUST |
| Logistics | Distance + estimated transport | MUST/SHOULD |
| Storage | Availability/cost context | SHOULD |
| Payment reliability | Trust/status factor | SHOULD |
| Buyer credentials | Trust/verification status | MUST |
| Arrival volumes | Store/display if source provides | SHOULD |
| Price trends | Chart/trend | SHOULD |
| Sale-window recommendation | Sell now/wait/monitor | SHOULD/MUST |
| Farmer/FPO matching | Matching engine | MUST |
| Verified buyers | Platform-review status | MUST |
| Lot creation | Farmer/FPO lot | MUST |
| Quality grading | A/B/C prototype | MUST |
| Digital offers | Offer workflow | MUST |
| Logistics coordination | Status/stub | SHOULD |
| Payment tracking | Transaction status | MUST |
| Dispute/grievance | Basic form + status | SHOULD |
| Price realization | Net-realization calculation | MUST |
| Information asymmetry | Unified intelligence view | MUST |
| Transaction cost | Cost estimates | SHOULD |
| FPO aggregation | Aggregation-ready model | SHOULD |
| Post-harvest loss | Storage + sale-window logic | SHOULD |
| Reliable buyer sourcing | Demand + trust + matching | MUST |
| Transparent transaction records | Offers/transactions/timestamps | MUST |

---

# 49. FINAL SCOPE CORRECTION

The earlier documentation is **not wrong**, but this audit adds several PS-specific items that must not be forgotten:

1. **Processors**
2. **Institutional buyers**
3. **Digital trading channels**
4. **Arrival volumes**
5. **Expected prices**
6. **Sale-window recommendation**
7. **Payment reliability**
8. **Buyer credentials**
9. **FPO aggregation**
10. **Post-harvest loss**
11. **Dispute/grievance**
12. **Transparent transaction records**
13. **Multiple selling channels**
14. **Raw price vs effective/net realization**
15. **Transaction status history**

These should now be treated as part of the final product specification.

---

# 50. FINAL PRODUCT — LOCKED

KisanLink is:

> **A market-intelligence and transaction-enablement platform for farmers/FPOs that compares multiple selling opportunities across mandis, processors and institutional/digital buyers, considers price, demand, quality, arrivals, distance, logistics, storage and buyer trust, recommends a suitable selling opportunity and time with an explainable reason, and then supports digital offers and transparent transaction tracking.**

### The core product loop

```text
DATA
 ↓
PRICE + DEMAND + ARRIVALS + QUALITY + LOCATION
+ LOGISTICS + STORAGE + BUYER TRUST
 ↓
MARKET / BUYER COMPARISON
 ↓
NET REALIZATION
 ↓
SALE-WINDOW + BUYER RECOMMENDATION
 ↓
EXPLAIN WHY
 ↓
LOT
 ↓
OFFER
 ↓
ACCEPT
 ↓
LOGISTICS STATUS
 ↓
PAYMENT STATUS
 ↓
TRANSACTION RECORD
 ↓
GRIEVANCE IF REQUIRED
```

This is the version that should be used as the source of truth for the 10-day implementation.
