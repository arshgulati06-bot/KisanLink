# KisanLink Frontend/Backend/Database Integration Audit

**Date:** 2026-09-11  
**Repository:** `D:\KisanLink`  
**Audit mode:** Read-only  
**Production changes:** None. No checkout, merge, reset, deletion, overwrite, migration, dependency installation, frontend change, backend change, or ML change was performed.

## Evidence Standard

- **VERIFIED:** Directly read from the current worktree or from `git show <branch>:<path>`.
- **NOT PRESENT:** The complete branch tree was inspected and contains no implementation for the feature.
- **NOT VERIFIED:** Runtime behavior or a claim requiring evidence not available in source was not established.

## 1. Executive Summary

The current `frontend` branch is safe to preserve as the base/source of truth.

Verified branch state:

- Current branch: `frontend`
- Current branch commit: `761f5b9a77f7fd088dc6001551bb32deb7885566`
- Friend branch: `backend`
- Friend branch commit: `b042d149104217cf56999a12a1513a2681bd5b15`
- Repository: `D:\KisanLink`

The frontend branch contains the working static frontend, Flask ML API, CSV-backed market-data pipeline, Chronos forecasting, P10/P50/P90 output, evaluator, sale-window decision engine, buyer matcher, ingestion validation, market intelligence, and market comparison.

The friend branch contains only a minimal Flask application foundation and a MySQL connectivity check. It has no database schema, tables, migrations, business models, repositories, services, authentication, CRUD APIs, market data, lots, offers, transactions, forecasting, ingestion, or executable tests.

**Recommendation:** Preserve the frontend branch unchanged as the base. Do not merge the friend branch wholesale. Adapt only the friend branch's database configuration concept and health-check concept later. Build any required relational business database as a new reviewed layer around the existing Chronos/data/API system.

## 2. Repository/Branch Verification

The following commands were executed against `D:\KisanLink` without checking out the friend branch:

```text
git status
git branch -a
git rev-parse frontend
git rev-parse backend
git ls-tree -r --name-only backend
```

Verified results:

```text
Current branch: frontend
frontend: 761f5b9a77f7fd088dc6001551bb32deb7885566
backend:  b042d149104217cf56999a12a1513a2681bd5b15
```

Current status reported:

```text
On branch frontend
Your branch is ahead of origin/frontend by 3 commits.
Untracked files:
  docs/FINAL_INTEGRATION_AUDIT.md
  docs/INTEGRATION_PLAN.md
```

The friend branch contains exactly these 17 tracked files:

```text
.env.example
backend/.gitignore
backend/app/__init__.py
backend/app/config/__init__.py
backend/app/config/db.py
backend/app/controllers/__init__.py
backend/app/middleware/__init__.py
backend/app/models/__init__.py
backend/app/repositories/__init__.py
backend/app/routes/__init__.py
backend/app/routes/health.py
backend/app/schemas/__init__.py
backend/app/services/__init__.py
backend/requirements.txt
backend/run.py
backend/tests/__init__.py
docs/00_MASTER_CONTEXT.md/KISANLINK_MASTER_DOCUMENTATION.md
```

## 3. Current Frontend Architecture

### Frontend files

Verified files:

- `frontend/index.html`
- `frontend/pages/auth.html`
- `frontend/pages/farmer.html`
- `frontend/pages/buyer.html`
- `frontend/js/api.js`
- `frontend/js/config.js`
- `frontend/js/price-forecast.js`
- `frontend/js/dashboard.js`
- `frontend/js/i18n.js`
- `frontend/js/notifications.js`
- `frontend/js/crop-quality.js`
- `frontend/js/chat-assistant.js`
- `frontend/js/step4-farmer.js`
- `frontend/css/`

The farmer UI contains price outlook, market intelligence, market comparison, sale-window output, lots, offers, transactions, buyer matching, ingestion freshness, and multilingual controls.

The buyer UI contains sourcing demands, matched lots, offers, and transaction display.

`frontend/js/dashboard.js` uses `DashboardStateManager` and browser `localStorage` for profiles, lots, demands, offers, and transactions. These are not currently durable server-side records.

### API client

`frontend/js/api.js` provides the shared client. It:

- Uses `http://localhost:5000/api` by default.
- Adds JSON headers.
- Adds a stored Bearer token when available.
- Uses a 90-second forecast timeout.
- Converts non-success responses into `ApiError`.

`frontend/js/price-forecast.js` owns the forecast UI, cascading selectors, forecast rendering, evaluation display, and sale-window rendering.

## 4. Current Chronos/ML Architecture

### ML files

Verified files:

- `ml/config.py`
- `ml/data_loader.py`
- `ml/forecaster.py`
- `ml/evaluator.py`
- `ml/run_forecast.py`
- `ml/decision_engine.py`
- `ml/buyer_matcher.py`
- `ml/ingest.py`
- `ml/visualizer.py`
- `ml/data/`

### Data input

`ml/data_loader.py` combines:

```text
ml/data/Agriculture_price_dataset.csv
ml/data/2022.csv
ml/data/2026.csv
```

It also includes `ml/data/ingested/records.csv` when present.

Canonical fields are:

```text
State, District, Market, Commodity, Variety, Grade,
Date, Min_Price, Max_Price, Modal_Price
```

### Filtering

`get_market_data()` filters by:

- Commodity
- State
- District
- Market

The loader strips trailing `APMC` from market names, normalizes strings, parses dates and prices, removes invalid rows, removes exact duplicates, and keeps market-specific selection.

### Preprocessing

`prepare_context()` performs:

- Daily aggregation.
- Long-gap detection.
- Recent continuous-segment selection.
- IQR winsorization of the forecast context.
- Context-length limiting.
- Chronos tensor creation.

### Chronos

`ml/forecaster.py` imports `ChronosPipeline` and loads:

```text
amazon/chronos-t5-tiny
```

The model is loaded once by `backend/app.py` during normal app creation.

### P10/P50/P90

`forecast_with_quantiles()` calls `pipeline.predict()` and calculates:

- P10: lower uncertainty bound
- P50: median forecast
- P90: upper uncertainty bound

Negative prices are clamped to zero. The configured horizon is seven days.

### Evaluation

`ml/evaluator.py` calculates:

- MAE
- RMSE
- MAPE
- Naive last-value baseline
- Seven-day moving-average baseline
- Chronos relative improvement versus naive

### Decision engine

`ml/decision_engine.py` uses forecast values, uncertainty, quantity, storage cost, and a minimum-benefit threshold to recommend `SELL_NOW` or waiting.

### Buyer matcher

`ml/buyer_matcher.py` uses weighted scoring:

- Price: 35%
- Quantity: 20%
- Quality: 20%
- Location: 15%
- Trust: 10%

### Ingestion

`ml/ingest.py` validates and normalizes records, rejects invalid values, handles duplicates, persists accepted records to CSV, logs rejections, and supports optional official-source fetching when configured.

## 5. Current Backend Architecture

The current base backend is `backend/app.py`.

It provides:

- Flask application creation.
- CORS.
- Request-size limits.
- Lazy app initialization.
- Combined CSV loading.
- Chronos model loading.
- Static frontend serving.
- Market dropdown endpoints.
- Forecast endpoint.
- Market intelligence.
- Market comparison.
- Sale-window endpoint.
- Buyer-demand endpoint.
- Buyer matching endpoints.
- Ingestion status and update endpoints.

The current backend stores the loaded DataFrame, Chronos pipeline, buyer seed records, and ingestion metadata in the Flask application extension/in-memory store.

## 6. Friend Backend Architecture

### `backend/app/__init__.py`

Actual implementation:

- Loads `.env` using `load_dotenv()`.
- Creates a Flask app.
- Sets `SECRET_KEY` from the environment or a fallback.
- Enables global CORS.
- Registers only `health_bp`.

No authentication, models, repositories, services, business routes, or ML integration exists.

**Decision: REJECT as a replacement.** It would remove the current backend and Chronos route registration.

### `backend/app/config/db.py`

Actual implementation:

- Imports `mysql.connector`.
- Reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`.
- Opens a MySQL connection.
- Returns `None` on connection errors.
- Provides `check_db_connection()`.

It has no schema, query layer, transaction handling, connection pool, repository layer, or persistence features.

**Decision: ADAPT.** Use the configuration concept later, rewritten for the current application.

### `backend/app/routes/health.py`

Actual endpoint:

```text
GET /api/health
```

It calls `check_db_connection()` and returns Flask/database status.

**Decision: ADAPT.** Add a sanitized health endpoint to the current backend later. Do not replace current routes.

### `backend/run.py`

Actual behavior:

- Calls the minimal friend app factory.
- Reads `PORT`.
- Binds to `0.0.0.0`.
- Uses `debug=True`.

**Decision: REJECT.** It conflicts with the current Chronos server launcher and is unsafe as a production launcher.

### Empty package files

The friend controllers, middleware, models, repositories, routes, schemas, services, and tests packages contain only `__init__.py` markers.

**Decision: REJECT.** No reusable implementation exists in those files.

### `.env.example`

Documents Flask and MySQL variables.

**Decision: ADAPT.** Use only as a future configuration reference.

### `backend/requirements.txt`

Contains Flask, Flask-CORS, MySQL connector, and python-dotenv.

**Decision: ADAPT.** Add dependencies only after design and compatibility review.

### Documentation

The tracked friend documentation file contains documentation but no executable backend or database implementation.

**Decision: REJECT for code integration.**

## 7. Complete Database Audit

### Current frontend branch

The current branch has no active relational database.

Verified:

- `databse/` exists but is empty.
- No tracked `schema.sql`.
- No migrations.
- No relational database initialization.
- No ORM models.
- No SQL repository layer.
- Market data is CSV-backed.
- Ingested records are CSV-backed.
- Business workflow state is browser-local.

### Friend backend branch

The friend branch has no database schema.

Verified absent from the complete tree:

- `schema.sql`
- SQL migration files
- Seed SQL
- Table declarations
- ORM models
- Repository queries
- Database initialization
- Foreign keys
- Indexes
- Constraints
- Persistence logic

The only database implementation is a MySQL connectivity check.

### Database engine

- Current frontend branch: no relational engine verified.
- Friend branch: MySQL connector dependency and connection helper verified.
- Actual MySQL connectivity: NOT VERIFIED.
- Actual database existence: NOT VERIFIED.

### Table-by-table audit

No friend database tables exist, so there are no friend columns, primary keys, foreign keys, relationships, indexes, constraints, or table implementations to import.

| Table | Current frontend branch | Friend backend branch | Purpose/future value | Decision |
|---|---|---|---|---|
| `users` | Not present relationally | Not present | Durable identity/authentication | ADAPT as new design |
| `farmer_profiles` | Local frontend profile | Not present | Farmer-owned application data | ADAPT as new design |
| `buyer_profiles` | Local frontend profile/seed fields | Not present | Buyer identity and trust metadata | ADAPT as new design |
| `crops` | CSV commodity values | Not present | Stable reference data | ADAPT as new design |
| `markets` | CSV geography/market values | Not present | Stable market reference data | ADAPT as new design |
| `market_data` | CSV and ingested CSV; actively used by Chronos | Not present | Historical/live market observations | ADAPT through canonical adapter |
| `price_forecasts` | Per-request Chronos output, not persisted | Not present | Optional reproducibility/cache layer | ADAPT later, not required initially |
| `buyer_demands` | JSON seed plus localStorage | Not present | Durable buyer requirements | ADAPT as new design |
| `lots` | localStorage | Not present | Durable farmer inventory | ADAPT as new design |
| `offers` | localStorage | Not present | Buyer/farmer offer workflow | ADAPT as new design |
| `transactions` | localStorage | Not present | Durable lifecycle and audit | ADAPT as new design |
| `ingestion_runs` | In-memory metadata and CSV/log | Not present | Source and freshness audit | ADAPT as new design |
| `market_data_sources` | Source labels in code/data responses | Not present | Provenance and official-source status | ADAPT as new design |
| Notifications | Demo/local UI | Not present | Secondary workflow feature | REJECT initially |
| Chronos/model state | In-memory ML object | Not present | ML runtime state | REJECT database replacement |

### Future relational relationships

These relationships are not present in either branch and are future design targets:

```text
users
  ├── farmer_profiles
  ├── buyer_profiles
  ├── lots
  ├── buyer_demands
  └── transactions

crops
  ├── market_data
  ├── lots
  └── buyer_demands

markets
  └── market_data

lots
  ├── offers
  └── transactions

buyer_demands
  └── offers

offers
  └── transactions
```

### Required future database controls

- Primary keys for every table.
- Foreign keys for ownership and relationships.
- Unique market observation key using market, crop, observed date, variety, and grade, with an explicit source-collision policy.
- Non-negative price and quantity constraints.
- Valid status transitions.
- Separate observed date from insertion/update timestamps.
- Indexes on crop/market/date.
- Indexes on owner/status.
- Source, unit, freshness, and provenance fields.
- Null for unavailable optional measurements rather than zero.

## 8. Table-by-Table Database Comparison

| Concept | Frontend branch implementation | Friend branch implementation | Better version | Decision | Chronos conflict |
|---|---|---|---|---|---|
| Users | No DB table; local prototype profiles | No table | Neither | ADAPT later | None if separate from market data |
| Farmer profiles | Local profile object | No table | Neither | ADAPT later | None |
| Buyer profiles | Local profile and seed trust fields | No table | Neither | ADAPT later | None |
| Crops | CSV strings | No table | Current CSV is operationally used | KEEP current values, ADAPT IDs later | IDs must map to strings |
| Markets | CSV strings with APMC normalization | No table | Current resolver is operationally used | KEEP current behavior, ADAPT IDs later | Must not change market identity |
| Market data | Canonical CSV pipeline | No table | Frontend branch | KEEP current pipeline; ADAPT DB mirror later | High; database must preserve exact fields and filtering |
| Forecasts | Chronos per request | No table | Frontend branch | KEEP current behavior; optional cache later | High; never replace Chronos |
| Buyer demands | JSON seed/localStorage | No table | Frontend branch currently has more behavior | ADAPT persistence later | Matcher fields must remain compatible |
| Lots | localStorage | No table | Neither | ADAPT persistent workflow later | None directly |
| Offers | localStorage | No table | Neither | ADAPT persistent workflow later | None directly |
| Transactions | localStorage | No table | Neither | ADAPT persistent workflow later | None directly |
| Ingestion metadata | In-memory plus CSV/log | No table | Frontend branch has working provenance behavior | ADAPT persistence later | Source/freshness must remain accurate |

No friend table is eligible for `TAKE` because no friend table exists.

## 9. API Comparison

| API | Current contract | Friend contract | Compatible? | Action | Breaking risk |
|---|---|---|---|---|---|
| `/api/commodities` | `GET`; returns CSV-derived commodities | Not present | No equivalent | KEEP | High if removed |
| `/api/states` | `GET` with commodity | Not present | No equivalent | KEEP | High |
| `/api/districts` | `GET` with commodity/state | Not present | No equivalent | KEEP | High |
| `/api/markets` | `GET` with commodity/state/district | Not present | No equivalent | KEEP | High |
| `/api/forecast` | `POST`; seven-day Chronos forecast with P10/P50/P90 | Not present | No | KEEP | Critical |
| `/api/market-intel` | `GET`; market-specific intelligence | Not present | No | KEEP | High |
| `/api/market-compare` | `GET`; district market comparison | Not present | No | KEEP | High |
| `/api/sale-window` | `POST`; decision-engine output | Not present | No | KEEP | Critical |
| `/api/buyer-demands` | `GET`; seed demand data with provenance | Not present | No | KEEP; adapt source later | Medium |
| `/api/buyer-match` | `POST`; weighted matcher output | Not present | No | KEEP; adapt data source later | High |
| `/api/buyer-matches` | `GET`; matcher alias | Not present | No | KEEP | Medium |
| `/api/ingest/status` | `GET`; freshness/source status | Not present | No | KEEP | Medium |
| `/api/ingest/update` | `POST`; validated bounded deduplicated ingest | Not present | No | KEEP | High/security |
| `/api/health` | Not present in current app | `GET`; Flask/MySQL status | New additive endpoint | ADAPT | Low if additive |
| Auth endpoints | Not present | Not present | No | ADAPT later | New contract |
| Lot endpoints | Not present | Not present | No | ADAPT later | New contract |
| Offer endpoints | Not present | Not present | No | ADAPT later | New contract |
| Transaction endpoints | Not present | Not present | No | ADAPT later | New contract |

## 10. Data Flow Comparison

### Current flow

```text
User selects commodity/state/district/market
  -> frontend/js/price-forecast.js
  -> POST /api/forecast
  -> backend/app.py
  -> ml.data_loader.get_market_data()
  -> ml.data_loader.prepare_context()
  -> ChronosPipeline.predict()
  -> P10/P50/P90
  -> ml/evaluator.py
  -> ml/decision_engine.py
  -> JSON response
  -> frontend forecast table/chart/sale-window UI
```

Buyer flow:

```text
Farmer lot in localStorage
  -> POST /api/buyer-match
  -> ml/buyer_matcher.py
  -> seed buyer demands JSON
  -> weighted match response
  -> frontend match UI
```

Ingestion flow:

```text
POST /api/ingest/update
  -> ml/ingest.py validation
  -> duplicate detection
  -> ingested/records.csv
  -> in-memory DataFrame refresh
  -> future forecast requests use updated data
```

### Safe friend integration point

The friend branch has no data flow to preserve. Its MySQL connection concept can eventually sit beside the current data flow:

```text
Frontend
  -> existing Flask API
  -> backend services
      ├── application database for users/lots/offers/transactions
      └── canonical market-data adapter
            -> existing ml/data_loader.py
                  -> existing Chronos/evaluator/decision engine
```

### Duplication and conflict risks

- Database market data could duplicate CSV rows.
- Database IDs could conflict with current string-based commodity/market filters.
- Database aggregation could mix markets.
- Database timestamps could replace actual observation dates.
- Persisted forecasts could be mistaken for current forecasts.
- Server-backed business state could diverge from localStorage during migration.

## 11. Authentication/User System Comparison

### Current frontend branch

- `frontend/js/api.js` can attach a Bearer token from localStorage.
- `frontend/pages/auth.html` is a role-selection/demo portal.
- No verified backend login, registration, password hashing, user table, or authorization middleware exists.

### Friend branch

- No authentication routes.
- No user model.
- No user table.
- No password handling.
- No authorization middleware.
- No sessions or token issuance.

**Decision: ADAPT as a future new feature, not TAKE from friend.**

Authentication must be added without changing the public market/forecast contract unnecessarily.

## 12. Feature Comparison

| Feature | Current frontend branch | Friend backend branch | Better version | Decision | Reason |
|---|---|---|---|---|---|
| Chronos forecasting | Working | Not present | Frontend | KEEP | Non-negotiable |
| P10/P50/P90 | Working | Not present | Frontend | KEEP | Required UI contract |
| Evaluation | Working | Not present | Frontend | KEEP | Existing metrics and baselines |
| Sale-window decision | Working | Not present | Frontend | KEEP | Existing decision engine |
| Buyer matching | Working weighted matcher | Not present | Frontend | KEEP | Existing explainable scoring |
| Market intelligence | Working | Not present | Frontend | KEEP | Existing API/UI behavior |
| Market comparison | Working | Not present | Frontend | KEEP | Existing API/UI behavior |
| Historical data loading | Working CSV pipeline | Not present | Frontend | KEEP | Required Chronos input |
| Ingestion | Working validated CSV append path | Not present | Frontend | KEEP | Friend has no ingestion |
| Database connection | Not present | MySQL connectivity helper | Friend concept | ADAPT | Useful only as infrastructure concept |
| Database schema | Not present | Not present | Neither | ADAPT later | New design required |
| Health route | Not present | Present | Friend concept | ADAPT | Additive and sanitized |
| Authentication | Not present | Not present | Neither | ADAPT later | New implementation required |
| Lots persistence | localStorage | Not present | Neither | ADAPT later | New DB/API feature required |
| Offers persistence | localStorage | Not present | Neither | ADAPT later | New DB/API feature required |
| Transactions persistence | localStorage | Not present | Neither | ADAPT later | New DB/API feature required |
| CORS | Global CORS | Global CORS | Current app has broader functionality | REJECT friend replacement | Do not replace current app |
| Startup | Chronos-aware app startup | Minimal debug server | Frontend | KEEP | Friend launcher conflicts |

## 13. Test Comparison

### Current branch tests

Tracked test files:

```text
tests/test_ml_pipeline.py
tests/test_ingest_api.py
tests/test_hardcode_audit.py
tests/diagnostic_market.py
tests/diagnostic_real_market.py
```

The tests cover ML/data behavior including:

- Gap detection.
- Winsorization.
- APMC normalization.
- Market filtering.
- Context tensor shape.
- Forecast length and non-negative values.
- Evaluation behavior.
- Ingestion API behavior.
- Hardcoded-data audits.

### Friend branch tests

Only this file exists:

```text
backend/tests/__init__.py
```

It contains no executable tests, fixtures, API tests, database tests, or integration tests.

### Test status

No complete pytest run or live runtime test was performed in this audit. Therefore:

- Current pytest result: **NOT VERIFIED**.
- Friend pytest result: **NOT VERIFIED**.
- Friend MySQL connectivity: **NOT VERIFIED**.
- Chronos live forecast in this audit: **NOT VERIFIED**.

No tests should be weakened to accommodate future integration.

## 14. KEEP / TAKE / ADAPT / REJECT Matrix

| Component | Frontend branch | Friend backend branch | Better version | Decision | Reason |
|---|---|---|---|---|---|
| Frontend pages/UI | Working | Not present | Frontend | KEEP | Source of truth |
| Frontend API client | Working | Not present | Frontend | KEEP | Existing contracts |
| Forecast UI | Working | Not present | Frontend | KEEP | P10/P50/P90 dependency |
| Flask ML backend | Working | Minimal factory | Frontend | KEEP | Friend would remove functionality |
| Chronos | Working | Not present | Frontend | KEEP | Must never be replaced |
| Data loader | Working | Not present | Frontend | KEEP | Canonical ML input |
| Evaluator | Working | Not present | Frontend | KEEP | Existing validation |
| Decision engine | Working | Not present | Frontend | KEEP | Existing business logic |
| Buyer matcher | Working | Not present | Frontend | KEEP | Existing explainable matcher |
| Ingestion | Working | Not present | Frontend | KEEP | Existing validation/deduplication |
| CSV datasets | Present and used | Not present | Frontend | KEEP | Forecast source of truth |
| MySQL configuration | Not present | Basic connection helper | Friend concept | ADAPT | Rewrite safely |
| Health endpoint | Not present | Present | Friend concept | ADAPT | Additive route only |
| Database schema | Not present | Not present | Neither | ADAPT later | Must design new schema |
| Users/auth | Not present | Not present | Neither | ADAPT later | New implementation required |
| Lots/offers/transactions | localStorage | Not present | Neither | ADAPT later | New persistence layer required |
| Friend app factory | Working base app exists | Minimal factory | Frontend | REJECT | Conflicts with Chronos API |
| Friend launcher | Current launcher exists | Debug/0.0.0.0 launcher | Frontend | REJECT | Unsafe/conflicting |
| Empty package markers | Implemented packages exist | Empty markers | Frontend | REJECT | No functionality |
| Friend documentation | Existing docs exist | Documentation only | Frontend | REJECT | No executable value |

## 15. Conflicts and Risks

- No friend database exists to copy, so a new schema is required.
- MySQL dependency may conflict with the current ML environment and must be tested.
- A database market-data source could duplicate or alter CSV history.
- ID-based database entities may break current string-based filtering.
- Cross-market aggregation would corrupt market-specific Chronos contexts.
- A database `created_at` must not replace the actual observation date.
- Persisted forecasts can become stale or be mistaken for live outputs.
- LocalStorage and future server state can diverge.
- Friend global CORS is not a replacement for deployment-specific policy.
- Friend debug startup must not be reused in production.
- Friend DB errors may expose infrastructure details.
- No friend auth or authorization exists.
- No atomic offer/transaction behavior exists.
- No indexes or constraints exist because no tables exist.
- Existing frontend API fields are high-risk compatibility points.
- Chronos model loading is expensive and must not be moved into database CRUD requests.

## 16. Recommended Integration Architecture

```text
Frontend UI
  |
  v
Existing frontend API contracts
  |
  v
Current Flask backend
  |
  +--> Application services
  |      |
  |      +--> Future relational DB
  |             users / profiles / lots / demands / offers / transactions
  |
  +--> Existing market-data adapter
         |
         +--> CSV and validated ingest fallback
         |
         +--> Optional future market_data DB projection
                    |
                    v
              Existing ml/data_loader.py
                    |
                    v
                 Chronos
                    |
                    v
              P10/P50/P90
                    |
                    v
                Evaluator
                    |
                    v
              Decision engine
                    |
                    v
     Buyer matcher / market intelligence / comparison
                    |
                    v
                 Frontend
```

### Database responsibilities

The future database should own:

- Users and profiles.
- Lots and ownership.
- Buyer demands.
- Offers.
- Transactions.
- Source and ingestion metadata.
- Optional reference entities for crops and markets.

### ML responsibilities

The existing ML subsystem should own:

- Market-data normalization.
- Market-specific filtering.
- Gap handling.
- Outlier handling.
- Chronos inference.
- P10/P50/P90.
- Evaluation.
- Sale-window logic.
- Buyer scoring.

Forecast results may optionally be cached in a database later for reproducibility, but the database must not become the source of forecasting logic or model state.

## 17. Exact Integration Order

### Phase 1: Database foundation

Files to create later:

- New migration/schema files.
- New DB configuration module based on the friend connection concept.
- New database tests.

Files not to touch:

- `ml/forecaster.py`
- `ml/data_loader.py` behavior
- `ml/evaluator.py`
- `ml/decision_engine.py`
- `ml/buyer_matcher.py`
- `frontend/js/price-forecast.js`

Tests:

- Fresh schema creation.
- Primary/foreign key behavior.
- Uniqueness.
- Nullability and check constraints.
- Migration rollback.

Rollback:

- Delete only the disposable staging database.
- Keep CSV source unchanged.

### Phase 2: Backend repositories/services

Files to create later:

```text
backend/app/models/
backend/app/repositories/
backend/app/services/
backend/app/controllers/
backend/app/routes/
backend/app/schemas/
```

Implement users, profiles, lots, demands, offers, and transactions.

Tests:

- Ownership.
- Validation.
- Status transitions.
- Atomic offer acceptance.
- Repository queries.

Rollback:

- Disable new business services and retain localStorage behavior.

### Phase 3: API adapters

Files to modify/create later:

- `backend/app.py` or registered route modules.
- `frontend/js/api.js` for additive business calls only.
- `frontend/js/config.js` for new endpoint constants.

Do not change existing forecast endpoint fields.

Tests:

- Request/response contracts.
- Error shapes.
- Authentication.
- Authorization.
- Idempotency.

Rollback:

- Disable new endpoints.

### Phase 4: Connect existing market-data flow

Files to modify later:

- `ml/data_loader.py`, only to add an opt-in adapter.
- `ml/ingest.py`, only for optional DB persistence.
- Backend data-store initialization.

Tests:

- CSV/DB record parity.
- Date and unit parity.
- Market-specific filtering.
- Duplicate handling.
- Source/freshness metadata.

Rollback:

- Switch back to CSV input.

### Phase 5: Connect existing Chronos pipeline

Do not replace Chronos. Connect only the canonical data adapter to the existing loader.

Tests:

- Same context length.
- Same context values.
- Same gap information.
- Same winsorization.
- Same forecast response shape.

Rollback:

- Restore CSV as the default source.

### Phase 6: Connect evaluator and decision engine

Keep `ml/evaluator.py` and `ml/decision_engine.py` unchanged unless a verified defect appears.

Tests:

- Holdout metrics.
- Baseline comparison.
- Sale-window decisions.
- Uncertainty behavior.

Rollback:

- Disable DB-backed source and use existing pipeline.

### Phase 7: Connect buyer matcher

Replace only the demand source behind `ml/buyer_matcher.py`.

Preserve:

- Weights.
- Request fields.
- Match response fields.
- Commodity mismatch behavior.

Tests:

- Same seed fixture versus DB fixture.
- Ranking parity.
- Missing-field handling.

Rollback:

- Restore JSON seed source.

### Phase 8: Frontend integration

Files to modify later:

- `frontend/js/api.js`
- `frontend/js/config.js`
- `frontend/js/dashboard.js`
- Farmer/buyer HTML only for loading and error states.

Keep forecast UI behavior unchanged.

Tests:

- Refresh persistence.
- Role ownership.
- Lot/demand/offer/transaction workflows.
- Existing forecast smoke tests.

Rollback:

- Keep localStorage behind a feature flag.

### Phase 9: End-to-end testing

Verify:

```text
login
  -> farmer lot / buyer demand
  -> market selection
  -> current Chronos forecast
  -> P10/P50/P90
  -> evaluator
  -> decision engine
  -> buyer matching
  -> offer
  -> transaction lifecycle
```

## 18. Migration Strategy

No friend schema migration is possible because no friend schema exists.

A future migration should:

1. Create a disposable staging database.
2. Create reviewed tables and constraints.
3. Import copies of CSV data only.
4. Compare row counts and duplicate keys.
5. Compare date ranges and market counts.
6. Compare canonical filtered fixtures.
7. Run `prepare_context()` against CSV and DB fixtures.
8. Require forecast parity or an explicitly approved difference.
9. Add business data only after market-data parity succeeds.
10. Keep CSV fallback until the new source is proven.

## 19. Rollback Strategy

The rollback boundary must be explicit:

- CSV remains the fallback market-data source.
- Existing `backend/app.py` remains the fallback API implementation.
- Existing localStorage remains the fallback business-state store.
- New database APIs are additive and feature-flagged.
- No migration may delete or rewrite historical CSV data.
- No Chronos file is replaced during integration.
- Revert only future integration commits, never reset the base branch during the work.

## 20. Testing Strategy

### Unit tests

- Data normalization.
- Market resolution.
- Gap detection.
- Winsorization.
- Quantile output.
- Evaluator metrics.
- Decision thresholds.
- Buyer-match weights.
- DB validation and repository behavior.

### API tests

- Existing dropdown routes.
- Forecast success and validation errors.
- Market intelligence and comparison.
- Sale-window output.
- Buyer demands and matching.
- Ingestion limits and duplicate handling.
- New auth/business routes.
- Additive health route.

### Database tests

- Schema creation.
- Migrations up/down.
- Primary/foreign keys.
- Unique observation keys.
- Index behavior.
- Nullability.
- Ownership.
- Transactionality.

### ML tests

Preserve all current ML tests, especially `tests/test_ml_pipeline.py`. Add CSV/DB parity tests without weakening existing assertions.

### Integration tests

- DB data -> canonical loader -> Chronos context.
- Ingestion -> persistence -> refreshed forecast.
- User -> lot/demand -> match -> offer -> transaction.

### Browser tests

- Forecast dropdowns.
- P10/P50/P90 rendering.
- Sale-window rendering.
- Market comparison.
- Buyer match workflow.
- Persistence after refresh.

Runtime test result in this audit: **NOT VERIFIED**. No full pytest, MySQL connection, or live Chronos request was run during this read-only comparison.

## 21. Final Verdict

1. **Is the current frontend branch safe to preserve?** Yes. It is the only branch containing the verified working frontend, Chronos, ML, forecast APIs, evaluator, decision engine, buyer matcher, and ingestion behavior.
2. **Which exact friend database tables are worth taking?** None. The friend branch has no tables.
3. **Which backend components are worth taking?** No component unchanged. The MySQL connection and health-check concepts are useful.
4. **Which components should be adapted?** `backend/app/config/db.py`, `backend/app/routes/health.py`, `.env.example`, and the MySQL dependency.
5. **Which should be rejected?** Friend app factory, launcher, empty scaffolding, documentation-only file, global replacement of CORS/startup, and any wholesale branch merge.
6. **What must never be replaced?** Chronos, data loader behavior, P10/P50/P90, evaluator, decision engine, buyer matcher, ingestion, market intelligence, market comparison, frontend UI, and current API contracts.
7. **Safest integration order?** Database design, repositories/services, additive APIs, optional data adapter, Chronos parity, evaluator/decision parity, buyer matcher data source, frontend persistence, end-to-end testing.
8. **Biggest risks?** Data duplication, market contamination, schema/API mismatch, stale data, localStorage/server divergence, unsafe auth, migration loss, and dependency conflicts.
9. **Is the friend database compatible with Chronos?** There is no friend database to assess. A future database can be compatible only through a canonical adapter preserving current market-data semantics.
10. **What exact files should be touched later?** New DB/migration files, backend models/repositories/services/routes, optional `ml/data_loader.py` adapter, optional `ml/ingest.py` persistence, additive `frontend/js/api.js` and `frontend/js/dashboard.js` changes. Do not touch the protected Chronos files unless a verified defect requires it.

## 22. Final Checklist

- [x] Current repository verified as `D:\KisanLink`.
- [x] Current branch verified as `frontend`.
- [x] Friend branch verified as `backend`.
- [x] Friend branch inspected directly with `git ls-tree` and `git show`.
- [x] Complete friend file tree obtained.
- [x] Friend database/schema checked.
- [x] Friend models/repositories/services/controllers checked.
- [x] Friend routes and health endpoint checked.
- [x] Friend authentication checked.
- [x] Friend tests checked.
- [x] Current frontend/API/ML files compared.
- [x] Current database status identified.
- [x] No friend database tables falsely claimed.
- [x] Chronos marked as protected.
- [x] Current API contracts marked as protected.
- [x] No production changes made.
- [x] No branches checked out or merged.
- [ ] Future schema design approved.
- [ ] Future migrations implemented.
- [ ] DB/CSV parity proven.
- [ ] Runtime and pytest verification completed.
- [ ] Integration explicitly authorized by the user.

**Final recommendation:** Keep the current `frontend` branch and Chronos/ML/API system intact. Do not import any friend business/database implementation because none exists. Adapt only the friend MySQL configuration and health-check ideas later, after designing and testing a new persistence layer around the existing system.
