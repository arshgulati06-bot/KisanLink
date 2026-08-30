# KisanLink Backend

Flask REST API for **SIH26132 — Strengthening market linkages and price discovery
for farmers**.

The API answers one question end to end:

> **What should this farmer do with this crop right now, and why?**

It does that by putting every selling channel — mandis, processors,
institutional buyers, aggregators, traders, and any live offer already on the
table — on the same footing, costing each one down to a **net realization**,
ranking them, advising on **when** to sell, and writing down the reasons.

---

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example .env        # then edit DB_PASSWORD and SECRET_KEY

# Create the MySQL database once, then build the schema and load the demo data
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS kisanlink_db"
python -m scripts.init_db --seed --test-data

python run.py                  # http://localhost:5000
```

Check it is alive:

```bash
curl http://localhost:5000/api/health
curl http://localhost:5000/api        # every route the API serves
```

### No MySQL installed?

Set `DB_BACKEND=sqlite` in `.env` and run the same commands. The whole API works
against SQLite — the same `database/schema.sql` drives both. This is also how
the test suite runs, so a schema mistake fails in CI rather than in the demo.

### Demo accounts

`database/test_data.sql` creates these. **All use the password `Kisan@123`.**

| Role | Phone | Who |
|---|---|---|
| Farmer | 9000000002 | Ramesh Patil, Ozar (Nashik) |
| Farmer | 9000000003 | Sunita Jadhav, Niphad |
| Farmer | 9000000004 | Vitthal Shinde, Rahuri |
| FPO | 9000000005 | Sahyadri Farmer Producer Company |
| Buyer (Processor) | 9000000010 | ABC Foods Processing |
| Buyer (Institutional) | 9000000011 | Statewide Institutional Supplies |
| Buyer (Aggregator) | 9000000012 | Krishi Aggregators LLP |
| Buyer (Trader) | 9000000013 | Pawar Trading Company |
| Admin | 9000000001 | Platform Administrator |

```bash
TOKEN=$(curl -s -X POST localhost:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"phone":"9000000002","password":"Kisan@123"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")

curl -s localhost:5000/api/lots?mine=true -H "Authorization: Bearer $TOKEN"
curl -s localhost:5000/api/lots/1/recommendation -H "Authorization: Bearer $TOKEN"
```

---

## Tests

```bash
pytest                 # 154 tests, ~17s, no MySQL required
pytest tests/test_recommendations -v
```

The suite builds a throwaway SQLite database from the **real**
`schema.sql` + `seed.sql` + `test_data.sql`, so it exercises the same SQL the
MySQL deployment uses. `tests/test_recommendations/test_end_to_end.py` walks the
entire demo path in one test — if that passes, the demo works.

---

## Layout

```
backend/
├── app/
│   ├── config/         settings.py (every tunable number) and db.py (data access)
│   ├── routes/         URL map only - one file answers "what endpoints exist?"
│   ├── controllers/    validate the request, call a service, wrap the response
│   ├── services/       business rules - the only layer that decides anything
│   ├── repositories/   the only layer that writes SQL
│   ├── models/         dataclasses mapping rows to objects (no ORM)
│   ├── schemas/        declarative request validation
│   ├── middleware/     authentication and role checks
│   └── utils/          response envelope, JWT/passwords, unit conversion
├── ml/                 forecasting, matching and the recommendation engine
├── database/           schema.sql, seed.sql, test_data.sql
├── scripts/            init_db, reset_db
└── tests/
```

**The layering rule:** controllers never touch SQL, repositories never make
decisions, and services never build HTTP responses. `database/schema.sql` is the
single source of truth for the data model.

---

## How the intelligence works

Nothing here is a black box, and nothing is trained on transaction history the
project does not have. Every number can be shown to a farmer and defended.

### 1. Net realization, not the headline price

Ranking on gross price is the mistake the problem statement exists to fix. Each
option is costed down:

```
net = gross - transport - mandi commission - market fee - storage - other
```

A mandi quoting ₹29.05/kg 181 km away can net less than one quoting ₹28.25/kg
54 km away. The API returns both figures, side by side, for every option.

### 2. Explainable weighted matching (`ml/matching_model.py`)

Five components, each scoring 0–1 with a sentence explaining itself:

| Component | Weight | What it measures |
|---|---|---|
| Price | 35% | Against the recent market benchmark, not against the other offers |
| Quantity fit | 20% | Both how much of the buyer's need the lot covers and how much of the lot they take |
| Quality | 20% | Grade A/B/C against the buyer's minimum, plus moisture limits |
| Distance | 15% | Road-distance estimate, with a district fallback when coordinates are missing |
| Trust | 10% | Platform verification, ratings, completed deals, payment punctuality, open grievances |

Weights are configuration (`.env`), not learned parameters, and the API says so
in its own response.

**When ranking on net realization the weights are rebalanced**: transport is
already inside the net price, so scoring distance at full weight would charge
the farmer for the same journey twice. Half the distance weight moves to price;
the rest stands for travel time and the difficulty of chasing a distant buyer.

### 3. Forecasting that knows when to stay quiet (`ml/forecast_model.py`)

Least squares and moving averages in plain Python — no numpy or scikit-learn,
because the model is small and readability matters more than speed.

- Under 10 observations it returns `available: false` and
  *"Insufficient historical data for a reliable forecast."* It never invents a
  number.
- When the trend fit is weak it falls back to a moving average and sets
  `trend_is_reliable: false`. The sale-window logic then refuses to advise
  holding stock on a direction it does not trust.

### 4. Sale window

Waiting is advised only when the projected gain clearly beats the cost of
holding — storage charges plus an allowance for physical loss — **and** the
forecast is trustworthy **and** storage actually exists nearby. A perishable
crop whose shelf life is shorter than the waiting window is never told to wait.

---

## Data honesty

The project rules are enforced in code, not just in documentation:

- Every price row carries its `source`; `is_official_source` is `true` only for
  AGMARKNET / data.gov.in / e-NAM. The seeded demo prices are tagged
  `SEED_DEMO` and the API labels them *"platform-entered or demonstration data,
  not official published market prices."*
- Demo buyers and storage facilities carry `is_seed_data = 1`. They are
  **not** real verified commercial buyers.
- `verification_status` is a **platform review**. Every buyer payload carries
  the disclaimer that it is not a government KYC or GST verification.
- Arrival volume is `NULL` when the source does not publish it — never zero.
- Transport, storage and distance figures are labelled estimates with their
  assumptions attached. No external mapping or freight API is called.

## What is deliberately not built

- **No payment gateway.** Payments are tracked as the parties report them.
- **No live logistics integration.** Transport requests are tracked; costs are
  modelled.
- **No computer-vision grading.** Grades are self-declared A/B/C.
- **No learned ranker.** A 10-day prototype has no transaction history to learn
  from, and a farmer told to accept a lower price deserves to see the arithmetic.

---

## API

The full contract — every endpoint, its request shape and its response — is in
[`API.md`](API.md). A live, machine-readable route list is at `GET /api`.

Every response uses one envelope:

```jsonc
// success
{ "success": true, "data": { }, "message": "..." }
// list endpoints add pagination
{ "success": true, "data": [], "meta": { "page": 1, "page_size": 20, "total": 42, "total_pages": 3 } }
// failure
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "...", "details": { "field": "why" } } }
```

Authenticate with `Authorization: Bearer <token>` from `/api/auth/login`.

## Database

21 tables. `python -m scripts.reset_db --yes --seed` drops and rebuilds them.

```
users ─┬─ farmer_profiles ─── fpo_members ─── fpo_profiles
       ├─ buyer_profiles ──── buyer_requirements
       └─ lots ─┬─ lot_contributions
                ├─ offers ─── transactions ─┬─ transaction_status_history
                │                           ├─ payments
                │                           ├─ ratings
                │                           └─ grievances
                └─ recommendations
crops ── market_data ── markets ── price_forecasts
storage_facilities        logistics_requests
```
