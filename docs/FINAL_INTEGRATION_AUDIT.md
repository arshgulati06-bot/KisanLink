# KisanLink Final Integration Audit

**Audit date:** 2026-09-11  
**Repository audited:** `D:\KisanLink` only  
**Audit mode:** Read-only analysis and integration planning  
**Production changes:** None. No branch checkout, merge, reset, delete, schema edit, dependency installation, dataset edit, or commit was performed.

## Evidence Labels

- **VERIFIED:** Directly observed in the current `D:\KisanLink` worktree or local Git metadata.
- **NOT PRESENT:** A targeted search of the verified current worktree found no implementation.
- **NOT VERIFIED:** Evidence was unavailable or insufficient. This is not a claim that the feature does not exist.

## 1. Executive Summary

The current `frontend` branch is the source of truth and must remain the integration base.

- **Base branch:** `frontend`
- **Base commit:** `761f5b9a77f7fd088dc6001551bb32deb7885566`
- **Friend branch selected for comparison:** local `backend`
- **Friend commit:** `b042d149104217cf56999a12a1513a2681bd5b15`
- **Repository path:** `D:\KisanLink`

The base architecture is a static HTML/CSS/JavaScript frontend connected to Flask, with a top-level Chronos ML pipeline. Historical mandi data is loaded from CSV files, normalized and filtered by market, passed through preprocessing, forecast with `amazon/chronos-t5-tiny`, reduced to P10/P50/P90, evaluated against holdout and baseline forecasts, and rendered by the existing frontend. Ingestion supports validated local records and optional official-source fetching.

The base branch does not currently contain a verified relational business database. The `databse/` directory is present but empty in the audited worktree. Lots, demands, offers, and transactions are currently represented primarily by frontend local state; buyer demands also have a labelled JSON seed source.

The friend branch's exact file tree and implementation could not be read safely with the available repository tools. Local Git metadata verifies its identity and two commits, but does not prove its schema, tables, APIs, models, repositories, tests, or authentication. Those items are therefore marked **NOT VERIFIED**, not assumed absent.

**Recommendation:** Do not merge the friend backend wholesale. First inspect and approve individual components. Preserve the current Chronos/data/API/frontend path. Eventually use a database for persistent application state and possibly as a market-data source through a canonical adapter, while keeping the existing ML preprocessing and forecasting semantics intact.

## 2. Current Frontend Branch Architecture

### Frontend: VERIFIED

Relevant base files include:

- `frontend/index.html`
- `frontend/pages/auth.html`
- `frontend/pages/farmer.html`
- `frontend/pages/buyer.html`
- `frontend/js/api.js`
- `frontend/js/price-forecast.js`
- `frontend/js/dashboard.js`
- `frontend/js/config.js`
- `frontend/js/i18n.js`
- `frontend/js/notifications.js`
- `frontend/js/crop-quality.js`
- `frontend/js/chat-assistant.js`
- `frontend/js/step4-farmer.js`
- `frontend/css/`

The farmer dashboard contains price outlook, market intelligence, market comparison, sale-window output, lots, offers, transactions, buyer matching, freshness messaging, multilingual controls, and crop-quality status. The buyer dashboard contains sourcing demands, matched lots, offers, and transaction display.

`frontend/js/dashboard.js` uses `DashboardStateManager` and browser `localStorage` for farmer profiles, buyer profiles, lots, demands, offers, and transactions. This is prototype persistence, not a verified backend database workflow.

### API: VERIFIED

The base frontend calls the Flask backend using `frontend/js/api.js`. The default API base is `http://localhost:5000/api`, and forecast requests use a 90-second timeout.

Existing contracts:

- `GET /api/commodities`
- `GET /api/states?commodity=`
- `GET /api/districts?commodity=&state=`
- `GET /api/markets?commodity=&state=&district=`
- `POST /api/forecast`
- `GET /api/market-intel`
- `GET /api/market-compare`
- `POST /api/sale-window`
- `GET /api/buyer-demands`
- `POST /api/buyer-match`
- `GET /api/buyer-matches`
- `GET /api/ingest/status`
- `POST /api/ingest/update`

### Backend: VERIFIED

`backend/app.py` is the Flask API entry point. It:

- Loads combined market data.
- Loads Chronos once during app creation unless explicitly disabled.
- Registers static frontend serving.
- Provides market dropdown, forecast, market-intel, market-compare, sale-window, buyer-demand, buyer-match, and ingestion endpoints.
- Enables CORS.
- Applies a request-size limit.
- Returns JSON error bodies.
- Uses an in-process store containing the DataFrame, model pipeline, buyer demands, and ingestion metadata.

There is no verified relational business database connection in this base backend.

### ML: VERIFIED

The top-level `ml/` directory contains:

- `config.py`
- `data_loader.py`
- `forecaster.py`
- `evaluator.py`
- `decision_engine.py`
- `buyer_matcher.py`
- `ingest.py`
- `run_forecast.py`
- `visualizer.py`
- `preprocessing/`
- `inference/`
- `training/`
- `evaluation/`
- `data/`

The exact contents of some subdirectories are not individually audited here; no assumption is made about whether they are active production paths.

### Data: VERIFIED

Historical files:

- `ml/data/Agriculture_price_dataset.csv`
- `ml/data/2022.csv`
- `ml/data/2026.csv`

Additional data paths include:

- `ml/data/buyers/demands.json`
- `ml/data/ingested/records.csv` when created
- `ml/data/ingested/ingest.log` when created
- `ml/data/_cache/combined.pkl` and its signature file when cache is created

The buyer JSON explicitly labels its rows as platform seed requirements, not a live procurement API.

### Database: VERIFIED / NOT PRESENT

The base branch has no verified active relational database schema in the current worktree.

- `databse/` exists but is empty: VERIFIED.
- A database schema used by the base backend: NOT PRESENT in the audited worktree.
- Database initialization/migrations used by the base runtime: NOT PRESENT in the audited worktree.
- CSV-backed analytical market data: VERIFIED.
- Browser-local business state: VERIFIED.

### Base data flow

```text
CSV files + persisted ingest CSV
  -> load_combined_data()
  -> normalize schemas, names, dates, prices
  -> exact deduplication and cache
  -> commodity/state/district/market filtering
  -> daily median, gap selection, winsorization
  -> Chronos context tensor
  -> Chronos P10/P50/P90
  -> evaluator and decision engine
  -> Flask API response
  -> frontend forecast and dashboard UI
```

Business-state flow is separate:

```text
frontend DashboardStateManager
  -> browser localStorage
  -> local lots, demands, offers, transactions
```

That second flow is the main future database integration target.

## 3. Current Chronos Pipeline

### Input data: VERIFIED

`ml/data_loader.py` combines three CSV sources into this canonical schema:

```text
State, District, Market, Commodity, Variety, Grade,
Date, Min_Price, Max_Price, Modal_Price
```

`ml/ingest.py` can append validated records to `ml/data/ingested/records.csv` and update the in-memory store.

### Filtering: VERIFIED

`get_market_data()` filters by:

- Commodity
- State
- District
- Market

Market names are normalized by stripping a trailing `APMC`. The base implementation does not silently fall back to another district/state/market. A fuzzy market resolution is used only for an unambiguous candidate.

### Preprocessing: VERIFIED

`prepare_context()`:

- Builds a daily price series.
- Detects long gaps using `MAX_GAP_DAYS`.
- Selects a suitable recent continuous segment when possible.
- Applies conservative IQR winsorization to the forecast context.
- Limits context to `MAX_CONTEXT_LENGTH`.
- Returns prices, dates, context length, gap information, outlier count, and a tensor.

### Model: VERIFIED

`ml/forecaster.py` imports `ChronosPipeline` and loads `amazon/chronos-t5-tiny` using configuration from `ml/config.py`. The Flask process loads the model once during app creation under normal startup.

### Forecast and P10/P50/P90: VERIFIED

`forecast_with_quantiles()` calls `pipeline.predict()` with the configured horizon and sample count. It calculates:

- P10 / lower bound
- P50 / median
- P90 / upper bound

Negative values are clamped to zero. The current configured horizon is seven days and the current sample count is twenty.

### Evaluation: VERIFIED

`ml/evaluator.py` evaluates a holdout window using:

- MAE
- RMSE
- MAPE
- Naive last-value baseline
- Seven-day moving-average baseline
- Chronos improvement relative to naive

Evaluation returns `None` when there are fewer than the configured minimum records.

### Sale-window decision: VERIFIED

`ml/decision_engine.py` compares forecast values to the latest historical price and accounts for:

- Quantity
- Storage cost per day
- Forecast interval width
- Minimum benefit threshold
- Data-quality warning

It returns `SELL_NOW` or a wait action with day-by-day analysis and an explanation. The frontend renders the API result; it does not own the recommendation algorithm.

### Buyer matcher: VERIFIED

`ml/buyer_matcher.py` ranks demands using weighted components:

- Price fit: 35%
- Quantity fit: 20%
- Quality match: 20%
- Location: 15%
- Buyer trust: 10%

Commodity mismatch is penalized. The input demands currently come from the server-loaded seed JSON rather than a durable buyer database.

### Frontend rendering: VERIFIED

`frontend/js/price-forecast.js`:

- Loads cascading commodity/state/district/market values.
- Calls `/api/forecast`.
- Renders seven forecast rows.
- Displays price, lower and upper bounds.
- Displays evaluation metrics.
- Displays sale-window action and reason.
- Displays data freshness, gap, and outlier notes.

## 4. Current Database

### Current database state

There is no verified relational database implementation in the current frontend branch worktree.

| Relevant table/entity | Current base implementation | Primary key | Foreign keys | Indexes | Actual usage |
|---|---|---|---|---|---|
| Users | NOT PRESENT as backend DB table; prototype profile/config data exists | N/A | N/A | N/A | Frontend prototype only |
| Farmer profiles | Browser-local/profile config data | Local object identity | N/A | N/A | Frontend only |
| Buyer profiles | Browser-local/profile config data | Local object identity | N/A | N/A | Frontend only |
| Crops/commodities | CSV `Commodity` values | N/A | N/A | Pandas filter columns | Used by dropdowns and ML filtering |
| Markets | CSV `Market`, `District`, `State` values | N/A | N/A | Pandas filter columns | Used by dropdowns, filtering, comparison |
| Market prices | CSV canonical rows and ingested CSV rows | No relational PK | N/A | Cache plus DataFrame filtering | Primary Chronos input |
| Forecasts | Per-request API output | N/A | N/A | N/A | Not stored in relational DB |
| Buyer demands | `ml/data/buyers/demands.json` plus local UI state | JSON `id` / local ID | N/A | N/A | Buyer matching and UI prototype |
| Lots | Browser-local `DashboardStateManager` state | Generated local ID | N/A | N/A | Farmer UI prototype |
| Offers | Browser-local state | Generated local ID | N/A | N/A | Farmer/buyer UI prototype |
| Transactions | Browser-local state | Generated local ID | N/A | N/A | UI lifecycle prototype |
| Ingestion metadata | In-memory Flask extension plus persisted ingest CSV/log | N/A | N/A | N/A | Status endpoint and data refresh |
| Notifications | Demo/local UI items | N/A | N/A | N/A | UI only |

The `databse/` directory name is itself a typo and is empty in the audited worktree. No destructive database migration or schema conflict can be verified on the base branch because no active base schema was found.

### What belongs in a future database

Eventually database-backed:

- Users and credentials.
- Farmer and buyer profiles.
- Crops and market reference entities, if stable IDs are needed.
- Lots and ownership/status.
- Buyer demands and ownership/status.
- Offers and offer status transitions.
- Transactions and lifecycle/audit records.
- Optional source/ingestion metadata.
- Optional market observation mirror, only behind a tested canonical adapter.

Remain CSV/data-pipeline based initially:

- Existing historical market source files.
- Chronos preprocessing semantics.
- Forecast model input contract.
- Existing forecast generation, evaluator, decision engine, and P10/P50/P90 logic.

Do not move into a database merely because a table is convenient:

- Chronos model state.
- Forecast algorithm behavior.
- Evaluator behavior.
- Decision-engine rules.
- Frontend display decisions.
- Provenance labels that are not backed by actual source metadata.

## 5. Friend Backend Architecture

### What is verified

Local Git metadata verifies:

- Friend branch identity used for this audit: `backend`.
- Friend branch commit: `b042d149104217cf56999a12a1513a2681bd5b15`.
- Friend history includes `a5fe109e`: `Initialize Flask backend foundation`.
- Friend history includes `b042d149`: `teammate env help`.
- The friend branch is separate from the later base commits that added the Chronos/data/frontend integration.

### What is not verified

A safe file-level read of the friend branch tree was not available through the current tool environment. Therefore the following are **NOT VERIFIED**:

- Every friend branch file.
- SQL schema and table list.
- Models and repositories.
- Controllers, services, and routes.
- Authentication implementation.
- Validation and error handling.
- Seed data.
- Database initialization or migrations.
- Friend API request/response contracts.
- Friend ingestion implementation.
- Friend tests and test results.
- Friend dependencies and environment behavior.
- Friend indexes, constraints, foreign keys, and transaction behavior.

The friend branch must not be judged better or worse on those components until its tree is inspected directly from Git without checkout or worktree mutation.

## 6. Database Comparison

| Feature/Table | Frontend Branch | Friend Branch | Better/Useful Part | Decision |
|---|---|---|---|---|
| Users/authentication | No verified persistent DB auth; frontend token helper only | NOT VERIFIED | No evidence for comparison | NOT VERIFIED |
| Farmer profiles | Local prototype state | NOT VERIFIED | Durable profiles would be useful | NOT VERIFIED |
| Buyer profiles | Local prototype state plus seed buyer fields | NOT VERIFIED | Durable ownership/trust metadata would be useful | NOT VERIFIED |
| Crops/commodities | CSV-derived strings used by current API and ML | NOT VERIFIED | Stable IDs could help, but must map to current values | ADAPT |
| Markets | CSV-derived geography with APMC normalization | NOT VERIFIED | Relational reference data could help | ADAPT |
| Market prices | Canonical CSV plus validated ingested CSV | NOT VERIFIED | Base pipeline is the proven Chronos-compatible source | ADAPT |
| Forecasts | Computed by Chronos per request | NOT VERIFIED | Chronos output must remain authoritative | REJECT friend replacement |
| Buyer demands | Seed JSON plus local state | NOT VERIFIED | Persistent demands would be valuable | ADAPT |
| Lots | Local browser state | NOT VERIFIED | Persistent lots are genuinely needed later | NOT VERIFIED |
| Offers | Local browser state | NOT VERIFIED | Persistent offers are genuinely needed later | NOT VERIFIED |
| Transactions | Local browser state | NOT VERIFIED | Durable transaction lifecycle is needed later | NOT VERIFIED |
| Ingestion metadata | In-memory metadata plus CSV/log | NOT VERIFIED | Source/freshness persistence may help | ADAPT |
| Primary keys | No relational keys | NOT VERIFIED | Must be proven before adoption | NOT VERIFIED |
| Foreign keys | Not applicable | NOT VERIFIED | Required for business entities | NOT VERIFIED |
| Indexes | DataFrame filter columns/cache | NOT VERIFIED | DB indexes may improve durable queries | NOT VERIFIED |
| Constraints | Ingestion validation and dedup keys | NOT VERIFIED | Must preserve base data-quality rules | ADAPT |
| Migrations | NOT PRESENT | NOT VERIFIED | Needed for safe future persistence | NOT VERIFIED |
| Seed/demo records | Clearly labelled CSV/JSON prototype data | NOT VERIFIED | Only explicitly labelled data is acceptable | REJECT unlabelled seeds |

The friend database cannot currently be declared compatible because its actual schema and queries are not verified.

## 7. API Comparison

| Endpoint/Feature | Frontend | Friend | Conflict? | Decision |
|---|---|---|---|---|
| Commodity list | `GET /api/commodities` | NOT VERIFIED | Unknown | KEEP base contract |
| State list | `GET /api/states?commodity=` | NOT VERIFIED | Unknown | KEEP base contract |
| District list | `GET /api/districts?commodity=&state=` | NOT VERIFIED | Unknown | KEEP base contract |
| Market list | `GET /api/markets?commodity=&state=&district=` | NOT VERIFIED | Unknown | KEEP base contract |
| Forecast | `POST /api/forecast` with seven-day P10/P50/P90 | NOT VERIFIED | Potentially critical | KEEP base contract; reject replacement |
| Market intelligence | `GET /api/market-intel` | NOT VERIFIED | Unknown | KEEP base contract |
| Market comparison | `GET /api/market-compare` | NOT VERIFIED | Unknown | KEEP base contract |
| Sale window | `POST /api/sale-window` | NOT VERIFIED | Potentially critical | KEEP base contract and decision engine |
| Buyer demands | `GET /api/buyer-demands` | NOT VERIFIED | Unknown | Adapt persistent source behind same fields |
| Buyer match | `POST /api/buyer-match` | NOT VERIFIED | Potentially critical | Keep matcher and request shape |
| Buyer match alias | `GET /api/buyer-matches` | NOT VERIFIED | Unknown | Preserve unless deprecation is tested |
| Ingestion status | `GET /api/ingest/status` | NOT VERIFIED | Unknown | Keep freshness/provenance semantics |
| Ingestion update | `POST /api/ingest/update` | NOT VERIFIED | Security-sensitive | Keep validation and add auth only deliberately |
| Auth | No verified backend endpoint | NOT VERIFIED | Unknown | Add only as additive API with compatibility adapter |
| Lots/offers/transactions | Local frontend state, no verified API | NOT VERIFIED | Unknown | Add additive persisted APIs later |

The friend endpoint inventory is not sufficiently evidenced to claim duplicate or missing routes. Existing frontend contracts must be preserved until exact friend contracts are read and tested.

## 8. Component-by-Component Decision

| Component | Friend Implementation | Needed? | Compatibility | Decision | Reason |
|---|---|---:|---|---|---|
| Chronos forecaster | NOT VERIFIED; user states friend branch has no Chronos | Yes, base already works | Must not be replaced | REJECT | Base Chronos is protected source of truth |
| P10/P50/P90 contract | NOT VERIFIED | Yes | Critical frontend dependency | REJECT replacement | Preserve current forecast response |
| Forecast evaluator | NOT VERIFIED | Yes | Critical ML behavior | REJECT replacement | Preserve holdout and baselines |
| Sale-window engine | NOT VERIFIED | Yes | Critical decision behavior | REJECT replacement | Preserve data-driven recommendation |
| Buyer matcher | NOT VERIFIED | Yes | Current field/weight contract works | REJECT replacement unless defect proven | Avoid arbitrary score changes |
| CSV data loader | NOT VERIFIED | Yes | Current loader is Chronos-compatible | ADAPT only | DB can feed canonical adapter later |
| Database schema | NOT VERIFIED | Eventually | Unknown | NOT VERIFIED | Cannot approve unseen schema |
| Database initialization | NOT VERIFIED | Eventually | Unknown | NOT VERIFIED | Need repeatable non-destructive tooling |
| Authentication | NOT VERIFIED | Eventually | Must map Bearer token and roles | NOT VERIFIED | Security review required |
| User/profile models | NOT VERIFIED | Yes eventually | Must support ownership | NOT VERIFIED | No evidence of implementation |
| Market models | NOT VERIFIED | Maybe | Must preserve APMC and string compatibility | ADAPT | Current ML uses normalized fields |
| Market-data repositories | NOT VERIFIED | Maybe | Must preserve dates/units/source | ADAPT | Database adapter must not contaminate forecast data |
| Lot persistence | NOT VERIFIED | Yes eventually | Must map current local fields | NOT VERIFIED | Useful but unseen |
| Offer persistence | NOT VERIFIED | Yes eventually | Must support state transitions | NOT VERIFIED | Useful but unseen |
| Transaction persistence | NOT VERIFIED | Yes eventually | Must be atomic/idempotent | NOT VERIFIED | Useful but unseen |
| Notifications | NOT VERIFIED | No first integration need | Unknown | REJECT initially | Defer until transaction events exist |
| Seed/demo data | NOT VERIFIED | No unless labelled | Provenance risk | REJECT unlabelled data | Never present demo as official |
| Repository/service separation | NOT VERIFIED | Yes if real | Must preserve current ML boundary | NOT VERIFIED | Need actual files |
| Validation | NOT VERIFIED | Yes | Must preserve ingestion validation | NOT VERIFIED | Need actual implementation |
| Error handling | NOT VERIFIED | Yes | Must map frontend `error` handling | ADAPT | Preserve base error contract |
| Logging | NOT VERIFIED | Useful | Must avoid sensitive leakage | NOT VERIFIED | Need actual logging code |
| Dependencies | NOT VERIFIED | Maybe | Must avoid Chronos conflicts | NOT VERIFIED | Need actual requirements |
| Tests | NOT VERIFIED | Yes | Must run against current architecture | NOT VERIFIED | No test result may be claimed |

## 9. What We Should Take From Friend

No friend component is approved for immediate taking because the friend branch implementation could not be read directly in this audit.

Conditional candidates, pending direct code evidence:

1. **Persistent user/authentication implementation**
   - File/class/table: NOT VERIFIED.
   - Need: durable users, password handling, roles, and authorization.
   - Future destination: backend auth models, repositories, middleware, and additive routes.
   - Adaptation: must preserve frontend `Authorization: Bearer` behavior and not protect public market endpoints accidentally.

2. **Farmer/buyer profile persistence**
   - File/class/table: NOT VERIFIED.
   - Need: ownership and durable identity for lots and demands.
   - Future destination: backend models/repositories/services.
   - Adaptation: map to current `FARMER_PROFILE` and `BUYER_PROFILE` fields.

3. **Lot, demand, offer, and transaction persistence**
   - File/class/table: NOT VERIFIED.
   - Need: move the current browser-local workflow toward server-backed state.
   - Future destination: additive business APIs, then `frontend/js/dashboard.js`.
   - Adaptation: preserve current IDs/status meanings or define an explicit mapping.

4. **Database initialization/migrations**
   - File: NOT VERIFIED.
   - Need: repeatable schema creation and controlled upgrades.
   - Future destination: new migration-owned database layer.
   - Adaptation: staging imports and rollback before production use.

5. **Repository/service patterns**
   - Files: NOT VERIFIED.
   - Need: isolate persistence from Flask routes and preserve the ML boundary.
   - Future destination: backend repositories/services.
   - Adaptation: do not route forecast calculation through a replacement model.

6. **Market-data persistence**
   - Files/tables: NOT VERIFIED.
   - Need: optional durable source metadata and queryable observations.
   - Future destination: a canonical DB adapter behind `ml/data_loader.py`.
   - Adaptation: preserve `State`, `District`, `Market`, `Commodity`, `Variety`, `Grade`, `Date`, and `Modal_Price` semantics.

## 10. What We Should NOT Take

- Any friend forecast implementation that replaces Chronos.
- Any friend API that removes or renames current `p10`, `p50`, `p90`, evaluation, confidence, freshness, gap, or sale-window fields without an intentional versioned adapter.
- Any unseen database schema, migration, repository, or service simply because its filename sounds useful.
- Any schema that merges observations across markets or collapses variety/grade/date distinctions.
- Any unlabelled demo or seed records represented as official market data or verified buyers.
- Any unauthenticated or unrestricted ingestion implementation.
- Any destructive migration, reset script, or data import that overwrites the CSV source before comparison.
- Any duplicate frontend API client, dashboard implementation, or local state manager.
- Any hardcoded forecast, market price, buyer score, or sale action.
- Notifications, payments, logistics, crop quality, or live API claims without verified implementation and tests.

## 11. Database Integration Plan

### Final boundary

```text
Frontend
  -> existing API contract
  -> backend routes/services
  -> existing Chronos/data pipeline for forecasts
  -> historical/live market observations

Database
  -> users/profiles
  -> lots/demands/offers/transactions
  -> optional markets/crops/market observations
  -> backend services
```

### Keep in the Chronos/data pipeline

- Historical CSV files during the migration period.
- Canonical data normalization.
- Market-specific filtering.
- Daily series construction.
- Gap detection.
- Winsorization.
- Chronos model loading and prediction.
- P10/P50/P90 calculation.
- Evaluator and baselines.
- Sale-window logic.
- Existing forecast response contract.

### Move to a database eventually

- Users and credentials.
- Farmer/buyer profiles.
- Crops and markets as reference data if stable IDs are needed.
- Lots and ownership/status.
- Buyer demands and ownership/status.
- Offers and status history.
- Transactions and lifecycle/audit history.
- Ingestion runs, source metadata, freshness, and provenance.

Market observations may eventually be mirrored into a database, but only through a canonical adapter that produces the same input contract as the current loader. CSV fallback must remain until forecast parity is proven.

### Proposed future tables

These are design targets, not current verified tables:

- `users`
- `farmer_profiles`
- `buyer_profiles`
- `crops`
- `markets`
- `market_data`
- `buyer_demands`
- `lots`
- `offers`
- `transactions`
- `ingestion_runs`
- `market_data_sources`

### Required constraints and indexes

- Unique market observation key: market + crop + observed date + variety + grade + source policy.
- Foreign keys from profiles, lots, demands, offers, and transactions.
- Ownership constraints for farmer/buyer actions.
- Valid status transitions for lots, offers, and transactions.
- Non-negative quantity and price checks.
- Actual observation date separate from `created_at` and ingestion time.
- Indexes on crop/market/date, owner/status, demand crop/status, offer lot/status, and transaction status.
- Explicit source and official/unofficial provenance.
- Null for unavailable optional values; never use zero to mean missing.

### Migration requirements

- No current migration is verified.
- Create a staging schema first.
- Import a copy of CSV data without changing the source files.
- Compare row counts, duplicate keys, date ranges, market counts, price distributions, and filtered fixtures.
- Run base and DB-backed `prepare_context()` on identical fixtures.
- Require forecast parity or an explained, approved difference.
- Keep rollback to CSV and browser-local state until all tests pass.

## 12. Integration Order

### Phase 1: Friend tree and schema verification

**Files to inspect, not modify:** friend branch tree, schema, requirements, migrations, models, repositories, routes, services, tests.

**Files to create later:** audit fixture and schema comparison notes.

**Files not to touch:** all production files, `ml/forecaster.py`, `ml/evaluator.py`, `ml/decision_engine.py`, frontend forecast files.

**Tests:** no integration tests yet; only read-only inventory and schema review.

**Rollback:** no worktree change.

### Phase 2: Database staging

**Modify/create later:** new database config, migration/schema files, staging import script, database tests.

**Do not touch:** Chronos implementation and existing forecast response.

**Tests:** schema creation, constraints, indexes, duplicate imports, rollback, CSV/DB row parity.

**Rollback:** discard staging database and restore CSV adapter as source.

### Phase 3: Backend models, repositories, and services

**Modify/create later:** backend models, repositories, services, auth middleware/config, app wiring.

**Do not touch:** forecast algorithm files.

**Tests:** user ownership, validation, offer acceptance atomicity, transaction transitions, repository tests.

**Rollback:** disable new business routes and retain local frontend state.

### Phase 4: Additive API integration

**Modify/create later:** route/controller modules, API adapter methods, endpoint tests.

**Do not touch:** existing forecast endpoint fields and frontend forecast renderer.

**Tests:** request/response contract tests, error shape, auth, ownership, idempotency.

**Rollback:** keep old routes and disable new routes by configuration.

### Phase 5: Optional DB-to-ML adapter

**Modify/create later:** `ml/data_loader.py`, `ml/ingest.py`, DB config, backend store initialization, parity tests.

**Do not touch unless a proven defect exists:** `ml/forecaster.py`, `ml/evaluator.py`, `ml/decision_engine.py`.

**Tests:** identical fixture, market filtering, dates, gaps, outliers, tensor values, P10/P50/P90 shape, evaluation, sale-window output.

**Rollback:** switch source back to CSV without changing Chronos.

### Phase 6: Connect existing frontend business state

**Modify/create later:** `frontend/js/api.js`, `frontend/js/config.js`, `frontend/js/dashboard.js`, farmer/buyer pages for loading/error states.

**Do not touch:** `frontend/js/price-forecast.js` unless a tested compatibility adapter is unavoidable.

**Tests:** refresh persistence, login, ownership, lot/demand/offer/transaction workflows, forecast smoke test.

**Rollback:** retain localStorage path behind a feature flag.

### Phase 7: End-to-end verification

**Tests:** login -> lot/demand -> market selection -> Chronos forecast -> P10/P50/P90 -> buyer match -> offer -> transaction lifecycle.

**Rollback:** disable DB-backed business state and use the base CSV/ML/API path.

## 13. API Compatibility Rules

The following contracts MUST NOT break:

1. `/api/forecast` remains `POST`.
2. Forecast request fields remain `commodity`, `state`, `district`, `market`, with optional `quantity_qtl` and `storage_cost_per_day`.
3. Forecast response retains seven forecast rows and `price`, `p10`, `p50`, `p90`, `price_low`, and `price_high`.
4. Forecast response retains latest price/date, date range, confidence, gap/outlier information, evaluation, and sale-window fields.
5. Market filtering remains commodity/state/district/market-specific.
6. No silent fallback to another market.
7. Existing dropdown endpoint names and query parameters remain valid.
8. Existing buyer matcher request fields remain valid.
9. Error responses retain an `error` value that the frontend client can display.
10. Data-source and freshness messages must not claim live official data without configured evidence.
11. P10/P50/P90 must continue to come from model samples, not hardcoded values.
12. Auth additions must be additive and must not unexpectedly block public market discovery.

## 14. Testing Plan

### Unit tests

- Canonical column normalization.
- APMC market resolution.
- Date and price validation.
- Gap selection.
- Winsorization.
- Forecast quantile shape and non-negativity.
- Evaluator metrics and baselines.
- Decision-engine thresholds and uncertainty.
- Buyer matcher weights, mismatch penalty, and provenance.

### API tests

- Dropdown cascade.
- Forecast success, missing fields, insufficient data, bad numeric inputs, and model unavailable.
- Market intelligence and comparison.
- Sale-window response.
- Buyer-demand and buyer-match contracts.
- Ingestion size, auth, validation, duplicate handling, and status.
- New auth/business APIs after they exist.

### DB tests

- Fresh schema creation.
- Migration up/down in disposable DB.
- PK/FK behavior.
- Uniqueness and duplicate imports.
- Nullability, checks, indexes, ownership, and cascade policy.
- Offer acceptance transactionality.
- CSV-to-DB canonical parity.

### ML tests

Preserve `tests/test_ml_pipeline.py`, including gap detection, winsorization, APMC resolution, market filtering, context shape, forecast length, non-negative values, and evaluation behavior. Add DB adapter parity tests without weakening existing assertions.

### Integration tests

- DB observations -> loader -> Chronos context.
- Ingest -> persistence -> refreshed forecast.
- User -> lot/demand -> matching -> offer -> transaction.
- Authenticated and unauthenticated route behavior.

### Browser/E2E tests

- Farmer forecast dropdown and response rendering.
- P10/P50/P90 table and chart.
- Sale-window action from API.
- Market comparison.
- Buyer demand and match flow.
- Persisted state after refresh/login.
- Error and stale-data UI.

### Runtime audit status

A complete startup, health, real forecast, database-connectivity, and pytest run was **NOT VERIFIED** in this audit because the terminal command wrapper was failing before executing commands. No test result is claimed. The report must not be interpreted as evidence that pytest or Chronos inference currently passes in this environment.

## 15. Risks

- Friend schema may use incompatible IDs, units, dates, or names.
- Duplicate CSV/database observations may distort Chronos context.
- Cross-market aggregation may contaminate market-specific forecasts.
- Database source may have stale data while the UI implies freshness.
- Forecast response changes could break `price-forecast.js`.
- Auth/token changes may break API client behavior.
- Browser-local state and database state may diverge during partial migration.
- Offer acceptance may race without a transaction.
- Unlabelled seed data may be presented as official or verified.
- Missing indexes may make market-history queries slow.
- Large CSV loading and Chronos inference are expensive.
- Ingestion must remain bounded and authenticated in deployed environments.
- CORS and error-message leakage require later security hardening.
- Database migrations may destroy or reinterpret data if not staged.
- Dependency additions may conflict with Chronos, Torch, Pandas, or the current environment.
- The friend branch identity could drift; reconfirm the exact commit before future integration.

## 16. Final Verdict

1. **Should we keep the frontend branch as base?** Yes. It is the verified source of truth and contains the working Chronos/frontend/API integration.
2. **Should the friend's backend be merged wholesale?** No. Its complete implementation is not verified, and wholesale merging would risk replacing or conflicting with Chronos and current contracts.
3. **Which database pieces should be taken?** No specific friend table is approved yet. Conditional candidates are users, profiles, lots, demands, offers, transactions, source metadata, and possibly markets/crops after direct schema review.
4. **Which backend pieces should be taken?** Only verified authentication, validation, repositories, services, business APIs, and migration tooling that pass compatibility and security tests.
5. **Which pieces should be adapted?** Market/crop reference data, market observation persistence, ingestion metadata, auth, and browser-local business workflows.
6. **Which pieces should be rejected?** Any replacement forecasting system, any unverified or destructive migration, hardcoded/demo data presented as real, incompatible API, unsafe ingestion, duplicate frontend/backend paths, and untested feature claims.
7. **What is the safest integration order?** Friend tree/schema verification, staging database, backend models/repositories/services, additive APIs, optional DB-to-ML adapter, incremental frontend persistence, full tests, end-to-end verification.
8. **What must NOT be changed?** Current Chronos model loading, `ml/data_loader.py` behavior, `ml/forecaster.py`, P10/P50/P90 semantics, evaluator, decision engine, buyer matcher, forecast API contract, and working forecast frontend.

## 17. Exact Future Integration Checklist

- [ ] Confirm `D:\KisanLink` and current branch before every integration session.
- [ ] Confirm `frontend` remains the base branch.
- [ ] Record the exact friend branch name and commit.
- [ ] Read the friend branch tree directly from Git without checkout or worktree mutation.
- [ ] Inventory every friend schema, table, migration, model, repository, service, route, test, and dependency.
- [ ] Verify whether friend branch contains Chronos; do not infer from filenames.
- [ ] Compare every friend table's PK, FK, nullability, types, constraints, indexes, and timestamps.
- [ ] Identify duplicate and destructive migrations before accepting anything.
- [ ] Build a staging database only after schema approval.
- [ ] Import copies of market data without modifying CSV sources.
- [ ] Compare CSV and DB row counts, keys, dates, markets, units, and price distributions.
- [ ] Confirm DB observations produce the same canonical loader frame.
- [ ] Confirm market-specific filtering is unchanged.
- [ ] Confirm Chronos context values and lengths match on fixed fixtures.
- [ ] Confirm P10/P50/P90 response fields remain unchanged.
- [ ] Confirm evaluator and sale-window outputs remain available.
- [ ] Add database-backed users/profiles only after auth and ownership tests pass.
- [ ] Add lots/demands/offers/transactions behind additive APIs.
- [ ] Preserve existing frontend API contracts.
- [ ] Keep CSV fallback until DB/ML parity is proven.
- [ ] Add ingestion source, freshness, authentication, size, and duplicate tests.
- [ ] Preserve all existing ML tests; never weaken them to accommodate integration.
- [ ] Run backend/API/DB/ML/integration tests successfully.
- [ ] Run browser/E2E smoke tests for farmer and buyer workflows.
- [ ] Verify refresh/login persistence and rollback behavior.
- [ ] Perform full end-to-end verification.
- [ ] Only then consider changing the default market-data source.
- [ ] Do not modify Chronos or the forecast contract unless a verified critical defect requires it.

**Final audit conclusion:** preserve the current frontend branch and Chronos system. Integrate only verified friend backend/database components around that system, in staged additive phases. The friend branch's exact implementation remains **NOT VERIFIED** in this audit because direct branch-tree extraction was unavailable; no unsupported friend feature has been promoted to an integration recommendation.
