# KisanLink API Contract

Base URL: `http://localhost:5000`
Auth: `Authorization: Bearer <token>` from `POST /api/auth/login`.
A live route list is served at `GET /api`.

## Response envelope

```jsonc
// success
{ "success": true, "data": { }, "message": "Optional human-readable note" }

// list endpoints
{ "success": true, "data": [ ], "meta": {
    "page": 1, "page_size": 20, "total": 42,
    "total_pages": 3, "has_next": true, "has_previous": false } }

// failure
{ "success": false, "error": {
    "code": "VALIDATION_ERROR",
    "message": "Some fields are invalid. Please correct them and try again.",
    "details": { "quantity": "'quantity' must be at least 0.01." } } }
```

**Error codes:** `VALIDATION_ERROR` (422), `UNAUTHORIZED` (401), `FORBIDDEN`
(403), `NOT_FOUND` (404), `CONFLICT` (409), `METHOD_NOT_ALLOWED` (405),
`INTERNAL_ERROR` (500).

**Pagination:** any list endpoint accepts `?page=1&page_size=20`
(max 100) and most accept `?order_by=column direction`.

**Roles:** `FARMER`, `FPO`, `BUYER`, `ADMIN`. Administrators pass every role
check. Ownership is checked separately in the service layer — being a `FARMER`
does not let you edit another farmer's lot.

---

## Auth — `/api/auth`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/register` | — | Create an account and its role profile |
| POST | `/login` | — | Exchange phone + password for a token |
| GET | `/me` | any | Current account and profile |
| PUT | `/me` | any | Update name, phone, email, language |
| POST | `/change-password` | any | Requires the current password |
| PUT | `/farmer-profile` | any | Save village, district, coordinates, land size |

**`POST /api/auth/register`**

```jsonc
{
  "name": "Ramesh Patil",
  "phone": "9876543210",          // required, 10 digits starting 6-9
  "password": "secret123",        // required, min 6
  "role": "FARMER",               // FARMER | FPO | BUYER | ADMIN
  "email": "ramesh@example.com",
  "district": "Nashik", "village": "Ozar",
  "latitude": 20.05, "longitude": 73.85,
  // BUYER only:
  "business_name": "ABC Foods", "buyer_type": "PROCESSOR", "gst_number": "...",
  // FPO only:
  "fpo_name": "Sahyadri FPC", "registration_number": "..."
}
```

Returns `201` with `{ token, token_type, expires_in, user, profile }`.
A new buyer is always created `UNVERIFIED` — signing up never confers
verification.

---

## Crops — `/api/crops`

| Method | Path | Auth |
|---|---|---|
| GET | `/` `?q=&category=&include_inactive=` | — |
| GET | `/categories` | — |
| GET | `/<crop_id>` | — |
| POST | `/` | ADMIN |
| PUT | `/<crop_id>` | ADMIN |
| DELETE | `/<crop_id>` | ADMIN — deactivates, never deletes |

Crops carry `is_perishable`, `shelf_life_days` and `grade_scale`; the first two
feed the sale-window advice.

---

## Lots — `/api/lots`

The farmer's unit of supply. Everything downstream hangs off one.

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/` | optional | Public list shows only open lots; `?mine=true` shows your own including drafts |
| POST | `/` | FARMER/FPO | Location falls back to your profile |
| GET | `/dashboard` | FARMER/FPO | Counts plus lots needing attention |
| GET | `/<id>` `?include_offers=true` | optional | |
| PUT | `/<id>` | owner | Quantity/grade/crop lock once a live offer exists |
| DELETE | `/<id>` | owner | Drafts only — withdraw instead to keep the record |
| POST | `/<id>/publish` | owner | DRAFT → LISTED |
| POST | `/<id>/withdraw` | owner | → CANCELLED, rejects standing offers |
| PUT | `/<id>/status` | owner | |
| GET | `/<id>/matches` | any | Ranked buyers, explained |
| GET | `/<id>/recommendation` | any | **The hero endpoint** |

Filters: `crop_id`, `status`, `district`, `state`, `grade`, `min_quantity`,
`max_quantity`, `available_from`.

**`POST /api/lots`**

```jsonc
{
  "crop_id": 1,                 // required
  "quantity": 1000,             // required, > 0
  "unit": "KG",                 // KG | QUINTAL | TONNE | BAG | DOZEN
  "grade": "A",                 // A | B | C, self-declared
  "moisture_percent": 8.5,
  "expected_price": 28,
  "variety": "Pusa Ruby",
  "harvest_date": "2026-08-27",
  "available_from": "2026-08-30", "available_until": "2026-09-11",
  "village": "Ozar", "district": "Nashik",
  "latitude": 20.05, "longitude": 73.85,
  "notes": "Sorted and graded on farm."
}
```

Lot statuses: `DRAFT → LISTED → OFFER_RECEIVED → SOLD`, plus `RESERVED`,
`EXPIRED`, `CANCELLED`.

---

## Market intelligence — `/api/markets`, `/api/prices`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/markets` `?q=&district=&market_type=` | — | Market directory |
| GET | `/api/markets/<id>` | — | |
| GET | `/api/markets/nearby` | — | Nearest markets + each one's latest price |
| GET | `/api/markets/<id>/arrivals?crop_id=&days=` | — | Arrival volume series |
| POST | `/api/markets` | ADMIN | |
| GET | `/api/prices?crop_id=&district=&state=` | — | Latest price per reporting market |
| GET | `/api/prices/overview?crop_id=` | — | Best/worst/average plus the **spread** |
| GET | `/api/prices/trends?crop_id=&market_id=&days=` | — | Series with a 7-day moving average |
| GET | `/api/prices/benchmark?crop_id=&unit=` | — | One reference price, unit-converted |
| POST | `/api/prices` | ADMIN | Record one observation (idempotent per market/crop/day) |
| POST | `/api/prices/bulk` | ADMIN | `{ "records": [...] }`, reports per-row failures |

`GET /api/markets/nearby` requires either `latitude`+`longitude` or `district`.

Every price payload carries `source` and `is_official_source`, and every list
carries a `data_note` stating plainly whether the numbers are official or
demonstration data. `arrival_quantity` is `null` when the source publishes none.

---

## Intelligence — `/api/recommendations`, `/api/matching`, `/api/forecast`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/recommendations` | any | Full recommendation, optionally stored |
| GET | `/api/recommendations/lot/<id>` | any | Same, not stored |
| GET | `/api/recommendations/lot/<id>/latest` | any | The last stored snapshot |
| GET | `/api/recommendations/lot/<id>/history` | any | Previous snapshots |
| POST | `/api/recommendations/sale-window` | any | Just the timing answer |
| POST | `/api/matching` | any | `{lot_id}` or `{requirement_id}` |
| GET | `/api/forecast?crop_id=&market_id=&horizon_days=` | — | Price forecast |
| GET | `/api/forecast/readiness?crop_id=` | — | Is there enough history to forecast at all? |

### `GET /api/lots/<id>/recommendation` — the hero response

```jsonc
{
  "lot": { }, "crop": { },
  "benchmark": { "available": true, "price": 27.1, "unit": "KG", "as_of": "2026-08-29" },

  "recommended_option": {
    "rank": 1, "option_type": "MARKET",         // MARKET | BUYER | OFFER
    "option_id": 3, "label": "Lasalgaon Mandi",
    "sublabel": "APMC market yard", "channel": "MANDI",
    "gross_price_per_unit": 28.25,
    "net_price_per_unit": 26.63,                // what the farmer actually keeps
    "quantity": 1000, "unit": "KG",
    "realization": {
      "gross_amount": 28250.0,
      "deductions": { "transport": 776.4, "commission": 847.36, "storage": 0, "other": 0 },
      "total_deductions": 1623.76,
      "net_amount": 26626.24,
      "deduction_percent": 5.75
    },
    "match_score": 74.0,
    "score_components": {
      "price":    { "score": 0.55, "weight": 0.425, "reason": "Price is close to the recent market price." },
      "quantity": { "score": 1.0,  "weight": 0.2,   "reason": "Buyer's requirement matches the full lot." },
      "quality":  { "score": 1.0,  "weight": 0.2,   "reason": "Lot grade A meets the required grade C." },
      "distance": { "score": 0.82, "weight": 0.075, "reason": "Approximately 54 km by road from the lot location." },
      "trust":    { "score": 0.85, "weight": 0.1,   "reason": "Regulated market yard (APMC/eNAM); ..." }
    },
    "blockers": [], "is_viable": true
  },

  "why_this_recommendation": [
    "Price is close to the recent market price.",
    "Lot grade A meets the required grade C.",
    "Approximately 54 km by road from the lot location.",
    "Estimated costs of Rs 1,624 (transport Rs 776, commission Rs 847) have already been subtracted, leaving Rs 26,626.",
    "Navi Mumbai Vashi Mandi quotes a higher net price (by Rs 0.01/kg), but this option was ranked first for a shorter distance. Both are shown so the choice stays with the farmer."
  ],

  "sale_window": {
    "recommendation": "SELL_NOW",               // SELL_NOW | CONSIDER_WAITING | MONITOR | INSUFFICIENT_DATA
    "confidence": "LOW",                        // LOW | MEDIUM | HIGH
    "expected_gain_per_unit": 0.0,
    "holding_cost_per_unit": 1.33,
    "net_benefit_per_unit": -1.33,
    "horizon_days": 7,
    "reasons": [ "..." ]
  },

  "comparison": [                                // the price-discovery table
    { "rank": 1, "label": "Lasalgaon Mandi", "channel": "MANDI",
      "gross_price_per_unit": 28.25, "net_price_per_unit": 26.63,
      "estimated_net_total": 26626.24, "distance_km": 54.4, "match_score": 74.0 }
  ],

  "options": [ ],                                // full detail for each row above
  "market_context": { "highest_price": ..., "lowest_price": ..., "price_spread": ..., "arrivals": { } },
  "price_forecast": { "available": true, "method": "MOVING_AVERAGE", "trend": "STABLE",
                      "trend_is_reliable": false, "confidence": "MEDIUM", "projections": [ ] },
  "storage": { "available": true, "holding_cost_per_unit": 1.33, "nearest_facility": { } },
  "weights": { "configured": { }, "applied": { }, "note": "..." },
  "disclaimer": "Transport, storage and net realization figures are estimates ..."
}
```

**Forecast when history is thin** — the API says so rather than guessing:

```jsonc
{ "available": false, "method": "INSUFFICIENT_DATA", "data_points": 5,
  "minimum_required": 10,
  "reason": "Insufficient historical data for a reliable forecast (5 price observations available, 10 needed)." }
```

---

## Buyers and demand — `/api/buyers`, `/api/buyer-demands`

| Method | Path | Auth |
|---|---|---|
| GET | `/api/buyers` `?buyer_type=&verification_status=&district=&q=` | — |
| GET | `/api/buyers/<id>` | — |
| GET | `/api/buyers/dashboard` | BUYER |
| PUT | `/api/buyers/profile` | BUYER |
| GET | `/api/buyer-demands` `?mine=true&crop_id=&status=` | any |
| POST | `/api/buyer-demands` | BUYER |
| GET | `/api/buyer-demands/<id>` | — |
| PUT | `/api/buyer-demands/<id>` | owner |
| POST | `/api/buyer-demands/<id>/close` | owner |
| GET | `/api/buyer-demands/<id>/matches` | any |

Buyer types: `PROCESSOR`, `INSTITUTIONAL`, `AGGREGATOR`, `TRADER`, `EXPORTER`,
`OTHER`.
Verification: `UNVERIFIED`, `DOCUMENTS_SUBMITTED`, `PLATFORM_REVIEWED`,
`REJECTED` — set only by an administrator, never by the buyer.

**`POST /api/buyer-demands`**

```jsonc
{
  "crop_id": 1,
  "required_quantity": 250, "unit": "QUINTAL",
  "min_grade": "B", "max_moisture_percent": 12,
  "price_min": 2600, "price_max": 3000,        // midpoint is used for ranking
  "delivery_mode": "DELIVERED_AT_BUYER",       // FARM_GATE | BUYER_PICKUP | DELIVERED_AT_BUYER
  "delivery_district": "Pune", "latitude": 18.76, "longitude": 74.23,
  "payment_terms_days": 7,
  "valid_from": "2026-08-30", "valid_until": "2026-09-29"
}
```

`FARM_GATE` and `BUYER_PICKUP` mean the **buyer** carries the transport cost —
the recommendation engine reflects that in the farmer's net realization.

`/matches` returns ranked lots plus an `aggregation` block:
`{ remaining_quantity, matched_quantity_available, fully_coverable, lots_needed }`.

---

## Offers — `/api/offers`

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/` `?scope=buyer\|seller\|all&status=&lot_id=` | any | Scoped to the caller |
| POST | `/` | BUYER | One live offer per buyer per lot |
| GET | `/<id>` | any | |
| GET | `/lot/<lot_id>` | lot owner | All live offers on your lot |
| POST | `/<id>/accept` | recipient | Creates the transaction |
| POST | `/<id>/reject` | recipient | |
| POST | `/<id>/counter` | seller | Marks the original `COUNTERED`, creates a linked offer |
| POST | `/<id>/withdraw` | issuing buyer | |

Statuses: `PENDING`, `ACCEPTED`, `REJECTED`, `WITHDRAWN`, `COUNTERED`,
`EXPIRED`.

Only the party an offer was sent **to** may accept it: a buyer's offer is
answered by the farmer, a farmer's counter by the buyer.

Accepting marks the lot `SOLD`, rejects every rival offer, debits the buyer's
requirement, and opens a transaction with its payment obligation.

---

## Transactions and payments — `/api/transactions`

| Method | Path | Auth |
|---|---|---|
| GET | `/` `?scope=&status=&crop_id=` | party |
| GET | `/summary` | any |
| GET | `/<id>` | party |
| PUT | `/<id>/status` | party |
| GET | `/<id>/history` | party |
| POST | `/<id>/payments` | party |
| GET | `/<id>/realization` | party |

Status flow — only these moves are accepted:

```
OFFERED → ACCEPTED → LOGISTICS_PENDING → IN_TRANSIT → DELIVERED
        → PAYMENT_PENDING → PAID → COMPLETED
```

with `CANCELLED` and `DISPUTED` as escapes. Every change is written to an
append-only history with who made it and when.

Recording a payment that covers the full amount advances the transaction to
`PAID` automatically. A part payment splits the obligation: the paid portion
becomes a `PAID` record and the balance stays outstanding under the same due
date. Overpayment is refused.

---

## FPO — `/api/fpo`

| Method | Path | Auth |
|---|---|---|
| GET | `/` `?district=&state=` | — |
| GET | `/<id>` | — |
| PUT | `/profile` | FPO |
| GET | `/dashboard` | FPO |
| GET | `/<id>/members` | — |
| POST | `/<id>/members` | FPO owner |
| PUT/DELETE | `/<id>/members/<member_id>` | FPO owner |
| GET | `/<id>/aggregation-candidates?crop_id=` | FPO owner |
| POST | `/<id>/aggregate` | FPO owner |
| GET | `/<id>/lots/<lot_id>/payouts` | any |

Members are added by `farmer_id` or by `phone`.

`POST /<id>/aggregate` with `{ "lot_ids": [12, 15, 18] }` pools member lots into
one FPO lot. All lots must be the same crop; the aggregate takes the **lowest**
grade among them, because a pooled consignment can only honestly be sold at the
quality of its weakest part. Source lots are cancelled and recorded as
contributions, so the payout splits pro rata when the deal settles. A lot with a
live offer is never eligible.

---

## Logistics — `/api/logistics`

| Method | Path | Auth |
|---|---|---|
| POST | `/estimate` | — |
| GET/POST | `/requests` | any |
| GET | `/requests/<id>` | any |
| PUT | `/requests/<id>/status` | requester |
| PUT | `/requests/<id>/provider` | requester |

`POST /estimate` takes either `distance_km`, or two locations to measure
between:

```jsonc
{ "quantity": 1000, "unit": "KG", "distance_km": 195 }
```

Response includes `estimated_cost`, `vehicle_type`, `trips`, a `breakdown`, and
the `assumptions` string — it is always labelled a planning estimate, never a
transporter's quotation. With no measurable distance it returns
`available: false` rather than a guess.

Request flow: `REQUESTED → ASSIGNED → IN_TRANSIT → DELIVERED`, with `CANCELLED`.

---

## Storage — `/api/storage`

| Method | Path | Auth |
|---|---|---|
| GET | `/facilities` `?district=&facility_type=&cold_only=` | — |
| GET | `/facilities/<id>` | — |
| POST | `/facilities` | ADMIN |
| GET | `/nearby` `?latitude=&longitude=` or `?district=` | — |
| POST | `/estimate` | — |

`POST /estimate` returns the storage charge, an expected-loss allowance
(doubled for perishables) and the combined `holding_cost_per_unit` that the
sale-window logic weighs against any forecast gain.

---

## Trust and grievances — `/api/trust`, `/api/grievances`

| Method | Path | Auth |
|---|---|---|
| GET | `/api/trust/buyers/<id>` | — |
| PUT | `/api/trust/buyers/<id>/verify` | ADMIN |
| GET | `/api/trust/verifications/pending` | ADMIN |
| POST | `/api/trust/ratings` | party to a completed deal |
| GET | `/api/trust/ratings/user/<id>` | — |
| GET/POST | `/api/grievances` | any |
| GET/PUT | `/api/grievances/<id>` | party or ADMIN |
| GET | `/api/grievances/dashboard` | ADMIN |

`GET /api/trust/buyers/<id>` returns the 0–100 score **with its components**, so
it can be interrogated rather than merely displayed:

```jsonc
{
  "trust_score": 60.88,
  "components": {
    "verification":           { "points": 30.0, "max_points": 30,  "detail": "Platform-Reviewed" },
    "ratings":                { "points": 4.38, "max_points": 25,  "detail": "4.5/5 from 1 rating(s)" },
    "completed_transactions": { "points": 1.5,  "max_points": 15,  "detail": "1 completed of 1 transaction(s)" },
    "payment_punctuality":    { "points": 25.0, "max_points": 25,  "detail": "100% of payments made on or before the due date" },
    "grievance_penalty":      { "points": -0.0, "max_points": -15, "detail": "No open grievances" }
  },
  "is_provisional": false,
  "disclaimer": "Verification reflects a KisanLink platform review. It is not a government KYC or GST verification."
}
```

Ratings need a `PAID` or `COMPLETED` transaction and are one per person per
deal. Grievance flow: `OPEN → UNDER_REVIEW → RESOLVED | REJECTED`, plus
`WITHDRAWN`. Only an administrator can resolve one; the person who raised it
may withdraw it; closing requires a written `resolution`.

---

## Health — `GET /api/health`

```jsonc
{
  "status": "healthy",            // healthy | degraded
  "message": "KisanLink Flask backend is up and the schema is loaded.",
  "database": { "connected": true, "backend": "mysql", "schema_ready": true,
                "missing_tables": [], "details": "..." }
}
```

`degraded` with `schema_ready: false` means the database is reachable but
`python -m scripts.init_db` has not been run.
