# KisanLink Integration Plan

**Date:** 2026-09-11  
**Scope:** Read-only comparison of the local `frontend` base branch and the local `backend` friend branch in `D:\KisanLink`.  
**Integration status:** No integration was performed. No production code, database, frontend, ML file, dependency, branch, or working-tree state was changed.

## Evidence Rules

- `VERIFIED` means directly observed in the checked-out `D:\KisanLink` worktree or local `.git` metadata.
- `NOT VERIFIED` means the claim could not be proven from the available local evidence without changing the worktree. It is not treated as true or false.
- `NOT PRESENT` means a targeted search of the verified base worktree found no implementation.
- This report does not infer that a feature is absent from a branch merely because it is absent from another branch.

## 1. Repository & Branch Verification

### Repository

| Item | Result | Evidence |
|---|---|---|
| Required repository path | `D:\KisanLink` | VERIFIED; directory contains `.git`, `frontend`, `backend`, `ml`, `tests`, `docs` |
| Current branch | `frontend` | VERIFIED; `.git/HEAD` contains `ref: refs/heads/frontend` |
| Base branch | `frontend` | VERIFIED from current HEAD and user instruction |
| Base commit | `761f5b9a77f7fd088dc6001551bb32deb7885566` | VERIFIED from `.git/refs/heads/frontend` |
| Friend branch | `backend` | VERIFIED as the local branch corresponding to the friend commits; exact ownership should still be confirmed with the teammate |
| Friend commit | `b042d149104217cf56999a12a1513a2681bd5b15` | VERIFIED from `.git/refs/heads/backend` and `FETCH_HEAD` |
| Local branches | `backend`, `claude-backend`, `frontend`, `main`, `ml` | VERIFIED from `.git/refs/heads` |
| Remote configured | `origin` -> `https://github.com/arshgulati06-bot/KisanLink.git` | VERIFIED from `.git/config` |
| Remote branch advertisements available locally | `frontend`, `backend`, `claude-backend`, `main`, `ml` | VERIFIED from `.git/FETCH_HEAD` |
| Current commit history | Frontend commits include frontend foundation, farmer/buyer dashboards, ML integration, combined datasets, and market intelligence | VERIFIED from `.git/logs/refs/heads/frontend` |
| Clean/dirty status | NOT VERIFIED | The terminal command wrapper was unavailable during this audit; no destructive status operation was attempted |

Important history evidence on the base branch:

- `8001519c`: Build farmer and buyer frontend dashboards.
- `7fb0a319`: Add multilingual UI, voice assistant, crop quality, and farmer actions.
- `737176bb`: Integrate ML forecasting with frontend.
- `5a22a004`: Combine historical mandi datasets for Chronos forecasting.
- `761f5b9a`: Integrate ML forecasting and market intelligence.

The friend branch history available locally contains:

- `a5fe109e`: Initialize Flask backend foundation.
- `b042d149`: teammate env help.

The friend branch is therefore the branch selected for comparison, but its complete tree-level inventory is marked `NOT VERIFIED` where it could not be safely read without a branch checkout or working-tree mutation.

## 2. Current Frontend Branch Architecture

### Frontend: VERIFIED

The base branch contains a static HTML/CSS/JavaScript frontend:

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

The farmer UI includes price outlook, market intelligence, market comparison, sale-window output, lots, offers, transactions, buyer matching, multilingual controls, ingestion freshness, and crop-quality status.

The buyer UI includes requirements, matched farmer lots, offers, and transaction display. Its operational state is currently browser-local through `DashboardStateManager` in `frontend/js/dashboard.js`.

### Frontend API boundary: VERIFIED

`frontend/js/api.js` and `frontend/js/price-forecast.js` call the current Flask server at `http://localhost:5000/api` by default. The current contract includes:

- `GET /api/commodities`
- `GET /api/states?commodity=`
- `GET /api/districts?commodity=&state=`
- `GET /api/markets?commodity=&state=&district=`
- `POST /api/forecast`
- `GET /api/market-intel`
- `GET /api/market-compare`
- `GET /api/buyer-demands`
- `POST /api/buyer-match`
- `GET /api/buyer-matches`
- `POST /api/sale-window`
- `GET /api/ingest/status`
- `POST /api/ingest/update`

The frontend expects the forecast response to contain `forecast[]` rows with `day`, `date`, `price`, `p10`, `p50`, `p90`, `price_low`, and `price_high`, plus `evaluation`, `confidence`, and `sale_window`.

### Base backend: VERIFIED

The base branch contains `backend/app.py`, a Flask API that loads the combined historical store, loads Chronos once, registers the endpoints above, enables CORS, limits request size, and provides JSON error responses.

The base backend is not a relational business backend. Lots, demands, offers, and transactions are currently represented by frontend local state, while buyer-demand matching uses a checked-in JSON seed file.

## 3. Current Chronos/ML Architecture

This is the protected foundation. It must remain the source of truth.

### VERIFIED files

- `ml/config.py`: model, horizon, context, gap, outlier, evaluation, and ingestion configuration.
- `ml/data_loader.py`: combines three CSV datasets, normalizes schemas, strips APMC suffixes, parses dates/prices, removes exact duplicates, adds filter columns, detects gaps, winsorizes outliers, and creates the Chronos context tensor.
- `ml/forecaster.py`: loads `amazon/chronos-t5-tiny` and produces q10/q50/q90 forecasts through `ChronosPipeline.predict`.
- `ml/evaluator.py`: holdout MAE/RMSE/MAPE and naive/MA7 baselines.
- `ml/decision_engine.py`: risk-adjusted sell-now versus wait decision using forecast values, uncertainty, quantity, and storage cost.
- `ml/buyer_matcher.py`: explainable weighted buyer matching using price, quantity, grade, location, and trust inputs.
- `ml/ingest.py`: canonicalization, validation, size/count limits, duplicate detection, persistence, rejection logging, and optional official API fetch.
- `ml/run_forecast.py`: CLI forecast path.
- `ml/preprocessing/`, `ml/inference/`, `ml/training/`, and `ml/evaluation/`: directories exist; targeted implementation inventory for every file in those directories is NOT VERIFIED and must not be assumed to be production code.

### Forecast flow: VERIFIED

```text
ml/data/*.csv
  -> ml.data_loader.load_combined_data()
  -> market-specific filtering
  -> daily median and gap handling
  -> IQR winsorization on context
  -> Chronos context tensor
  -> ml.forecaster.forecast_with_quantiles()
  -> P10/P50/P90
  -> ml.evaluator.evaluate_model()
  -> ml.decision_engine.recommend_sale_window()
  -> POST /api/forecast
  -> frontend/js/price-forecast.js
```

The base branch's current forecast is not to be replaced by the friend branch. In particular, preserve:

- Chronos model loading and `amazon/chronos-t5-tiny`.
- `ml/data_loader.py` preprocessing and market-specific selection.
- P10/P50/P90 output semantics.
- Evaluation and baseline comparisons.
- Sale-window decision logic.
- Buyer matching logic unless a verified defect is found.
- Existing frontend forecast rendering and API field names.

## 4. Friend Backend Architecture

### VERIFIED from local git metadata

- The selected friend branch is local `backend` at `b042d149104217cf56999a12a1513a2681bd5b15`.
- Its visible commit history contains a Flask backend foundation and teammate environment help.
- It is separate from the current `frontend` branch and does not contain the base branch's later Chronos integration commits according to the local branch history.

### NOT VERIFIED

The following friend-branch details could not be proven from the current worktree without checking out or mutating branches, and therefore must be verified before any integration decision becomes executable:

- Complete friend branch file tree.
- Friend database schema, migrations, seed files, and every table.
- Friend models, repositories, controllers, services, route map, and tests.
- Friend authentication implementation and token contract.
- Friend API request/response shapes.
- Friend database engine and initialization commands.
- Friend indexes, foreign keys, nullable fields, cascade behavior, and transaction semantics.

No friend feature is classified as `TAKE` on the basis of name alone. The friend branch must be inspected by a safe read-only tree/diff operation in a follow-up before implementation begins.

## 5. Database Comparison

### High-level result

The current base branch has a file-backed analytical data store, not a relational application database. The friend branch's database structure is NOT VERIFIED. Consequently, no friend table can yet be approved for direct adoption.

| Table/Feature | My Branch | Friend Branch | Which is Better | Final Decision | Reason |
|---|---|---|---|---|---|
| Historical market price records | CSVs in `ml/data/` plus `ingested/records.csv` | NOT VERIFIED | Base is proven compatible with Chronos | KEEP MINE for forecast input; optionally mirror into DB | Loader already consumes canonical columns and metadata |
| Market geography dimensions | Derived from CSV columns | NOT VERIFIED | Base is proven and frontend-compatible | KEEP MINE initially | Avoid changing dropdown/filter semantics |
| Forecast results | Computed per request; not relationally cached | NOT VERIFIED | Base is the only proven P10/P50/P90 implementation | KEEP MINE | Friend has no verified Chronos-compatible forecast contract |
| Users/authentication | No persistent backend auth; token helper exists in frontend | NOT VERIFIED | NOT VERIFIABLE | MERGE/ADAPT only after review | Must preserve frontend token behavior and avoid fake auth |
| Farmer profiles | Prototype data/local state | NOT VERIFIED | NOT VERIFIABLE | MERGE/ADAPT | Needed for durable lots but no friend schema evidence yet |
| Buyer profiles | Seed/local state | NOT VERIFIED | NOT VERIFIABLE | MERGE/ADAPT | Needed for durable trust and demand ownership |
| Crops/commodities | CSV commodity values and frontend config | NOT VERIFIED | Base is proven for forecasting; friend may offer normalized IDs | MERGE | Add stable IDs only through a compatibility layer |
| Markets | CSV geography fields and current market resolver | NOT VERIFIED | Base is proven for current UI | MERGE | Preserve exact market normalization and APMC resolution |
| Market observations | Canonical CSV schema: State, District, Market, Commodity, Variety, Grade, Date, Min_Price, Max_Price, Modal_Price | NOT VERIFIED | Base is proven for ML; friend cannot replace it without adapter | MERGE | A relational mirror must expose the same canonical loader fields |
| Lots | Browser local state in `frontend/js/dashboard.js` | NOT VERIFIED | NOT VERIFIABLE | TAKE/ADAPT only after proof | Persistent lots are useful, but IDs/statuses must map to UI |
| Buyer demands | `ml/data/buyers/demands.json` seed plus browser state | NOT VERIFIED | NOT VERIFIABLE | MERGE/ADAPT | Preserve seed provenance and matcher input names |
| Offers | Browser local state only | NOT VERIFIED | NOT VERIFIABLE | TAKE/ADAPT only after proof | Useful workflow, but requires ownership and status constraints |
| Transactions | Browser local state only | NOT VERIFIED | NOT VERIFIABLE | TAKE/ADAPT only after proof | Useful lifecycle, but requires atomic offer acceptance |
| Price forecasts cache | No verified relational cache | NOT VERIFIED | NOT VERIFIABLE | REJECT friend replacement; consider future mirror | Forecast computation remains Chronos-owned |
| Notifications | Demo/local UI items | NOT VERIFIED | NOT VERIFIABLE | REJECT unless friend has durable, tested implementation | Not required for first safe integration |
| Foreign keys/cascades | Not applicable to current CSV store | NOT VERIFIED | NOT VERIFIABLE | REQUIRE review before acceptance | Must prevent orphaned lots/offers/transactions |
| Indexes | Pandas filter columns and cache | NOT VERIFIED | Base is optimized for current file-backed path | MERGE/ADAPT | DB indexes must support crop/market/date queries without changing API |
| Seed data | Historical CSVs and clearly labelled buyer seed | NOT VERIFIED | NOT VERIFIABLE | KEEP MINE; reject unlabelled friend seed | Data provenance must remain explicit |

### Required relational target, if later approved

A future relational mirror should at minimum contain stable entities for:

- `users`
- `farmer_profiles`
- `buyer_profiles`
- `crops`
- `markets`
- `market_data`
- `lots`
- `buyer_demands`
- `offers`
- `transactions`

The relational `market_data` projection must preserve the Chronos input contract: market, crop/commodity, date, and modal price, with variety/grade where available. It must preserve source and freshness metadata. It must not silently replace missing observations with zero or another market's prices.

## 6. Backend Feature Comparison

Because the friend tree is not safely readable in the current worktree, the following decisions are gated:

| Feature | Base status | Friend status | Decision | Integration condition |
|---|---|---|---|---|
| Authentication | Frontend token storage/helper only; no verified backend auth | NOT VERIFIED | MERGE/ADAPT | Friend auth must expose a token contract compatible with `Authorization: Bearer`, with password hashing and role checks |
| Users/farmer profiles | Prototype/local | NOT VERIFIED | TAKE/ADAPT | Must add ownership, validation, and stable IDs without changing forecast request fields |
| Buyer profiles/trust | Seed/local | NOT VERIFIED | TAKE/ADAPT | Must distinguish platform review from government KYC/GST verification |
| Crops/markets | Derived from CSV | NOT VERIFIED | MERGE/ADAPT | Preserve current dropdown values and APMC normalization |
| Market data/history | Working Chronos CSV pipeline | NOT VERIFIED | KEEP MINE + optional DB adapter | DB reads must produce the same canonical DataFrame and preserve market-specific filtering |
| Lots | Local browser state | NOT VERIFIED | TAKE/ADAPT | Backend must persist lot status and ownership; frontend can be connected later |
| Buyer demands/matching | Seed JSON plus working matcher | NOT VERIFIED | MERGE/ADAPT | Keep `ml/buyer_matcher.py`; friend persistence may replace only the seed source |
| Offers | Local browser state | NOT VERIFIED | TAKE/ADAPT | Require idempotent creation, ownership, status transitions, and conflict handling |
| Transactions | Local browser state | NOT VERIFIED | TAKE/ADAPT | Offer acceptance must be atomic and test status transitions |
| Recommendations | Sale-window and market intelligence are working | NOT VERIFIED | KEEP MINE; adapt persistence only | No friend recommender may replace Chronos/decision-engine outputs |
| Notifications | Demo/local | NOT VERIFIED | REJECT for first integration | Add only after durable transaction events exist |
| Logistics/storage | No verified durable API in base | NOT VERIFIED | NOT VERIFIED | Defer until exact contracts and cost assumptions are proven |

## 7. API Comparison

### Base API: VERIFIED

The current base API is the compatibility contract:

| Method | Endpoint | Base request/response requirement |
|---|---|---|
| GET | `/api/commodities` | Returns commodity list used by forecast dropdown |
| GET | `/api/states` | Requires `commodity` |
| GET | `/api/districts` | Requires `commodity`, `state` |
| GET | `/api/markets` | Requires `commodity`, `state`, `district` |
| POST | `/api/forecast` | Requires commodity/state/district/market; returns 7-day P10/P50/P90, evaluation, confidence, sale window |
| GET | `/api/market-intel` | Market-specific current/history metadata |
| GET | `/api/market-compare` | District market comparison |
| POST | `/api/sale-window` | Forecast-backed decision output |
| GET | `/api/buyer-demands` | Seed/provenance-labelled demands |
| POST | `/api/buyer-match` | Weighted match against demand data |
| GET | `/api/buyer-matches` | Query-form matcher alias |
| GET | `/api/ingest/status` | Dataset freshness and official-source status |
| POST | `/api/ingest/update` | Validated, bounded, deduplicated ingestion |

### Friend API comparison

Friend endpoint inventory: `NOT VERIFIED`. No endpoint may replace a base endpoint until a side-by-side request/response comparison is completed.

Rules for later API adaptation:

1. Preserve `/api/forecast` method, required fields, response field names, and P10/P50/P90 semantics.
2. Preserve market-specific filtering; no fallback to a different market without an explicit response field and user-visible explanation.
3. Add durable business endpoints under separate resources rather than overloading forecast routes.
4. Use versioned or compatibility-tested payload adapters if friend field names differ.
5. Preserve base error behavior sufficiently for `ApiClient` to surface `error` messages.

## 8. Data Compatibility

### Current data contract: VERIFIED

Canonical market record fields are:

```text
State, District, Market, Commodity, Variety, Grade,
Date, Min_Price, Max_Price, Modal_Price
```

The loader additionally creates lowercase filter columns and uses a combined cache. It strips trailing `APMC`, title-cases geography/commodity values, parses dates, drops invalid date/modal-price rows, removes exact duplicates, and sorts chronologically.

### Compatibility requirements

A future database adapter must:

- Return one canonical row per market/crop/date/variety/grade observation.
- Preserve `Modal_Price` as numeric and positive.
- Preserve the actual observation date rather than insertion time.
- Preserve source and freshness metadata.
- Avoid duplicate rows across imported CSV and database sources.
- Make date and market filters deterministic.
- Keep missing arrival/optional fields as null rather than zero.
- Support the current `prepare_context()` output without changing Chronos code.
- Keep historical CSV fallback available during migration and rollback.

### Possible mismatch points

- Friend database may use IDs where the base pipeline currently uses normalized strings.
- Friend schema may call the date `price_date`, `arrival_date`, or `created_at`; an explicit adapter is required.
- Friend price units may differ from the base QTL assumptions.
- Friend uniqueness may omit variety/grade and collapse distinct observations.
- Friend seed rows may be mistaken for official data.
- Friend queries may aggregate across markets, which would contaminate a market-specific forecast.
- Friend timestamps may describe ingestion rather than the actual market observation.

## 9. Chronos Compatibility

### Answer: conditionally yes, but not by direct replacement

A friend relational database can support the existing Chronos pipeline only if it supplies an adapter producing the same canonical DataFrame consumed by `ml.data_loader.py`, or if `ml/data_loader.py` is deliberately extended with a database source while retaining the current CSV path.

The safe architecture is:

```text
DB market_data + historical CSV fallback
  -> canonical data adapter
  -> existing ml.data_loader normalization/filtering
  -> existing prepare_context
  -> existing Chronos forecaster
  -> existing P10/P50/P90 API
  -> existing frontend
```

Do not connect a new database directly to `ChronosPipeline.predict` until duplicate handling, dates, units, market identity, and freshness have been tested.

The friend's non-Chronos forecast, if present, must be `REJECT` as a replacement. It may be reviewed only for non-conflicting metadata or persistence ideas.

## 10. KEEP FROM MY BRANCH

These are the base foundation and must remain:

- `frontend/` farmer, buyer, auth, dashboard, forecast, market comparison, and API wiring.
- `frontend/js/api.js` compatibility boundary.
- `frontend/js/price-forecast.js` P10/P50/P90 rendering and sale-window display.
- `frontend/js/config.js` endpoint names and 90-second ML timeout.
- `frontend/js/dashboard.js` as the UI workflow reference for lots, demands, offers, and transactions.
- `backend/app.py` route behavior and JSON contract, subject to future hardening.
- `ml/config.py` Chronos and preprocessing configuration.
- `ml/data_loader.py` normalization, market resolution, gap handling, winsorization, and context construction.
- `ml/forecaster.py` and Amazon Chronos model loading.
- `ml/evaluator.py` and baseline metrics.
- `ml/decision_engine.py` and explainable sale-window behavior.
- `ml/buyer_matcher.py` and weighted, explainable matching.
- `ml/ingest.py` validation, bounds, deduplication, persistence, and provenance behavior.
- `ml/data/Agriculture_price_dataset.csv`, `2022.csv`, and `2026.csv` as historical sources unless a separately verified migration supersedes them.
- `ml/data/buyers/demands.json` as explicitly labelled seed data.
- Existing API error and freshness semantics.
- Existing tests in `tests/test_ml_pipeline.py` and all Chronos regression expectations.

## 11. TAKE FROM FRIEND

Current decision: **nothing is approved for immediate taking**, because the friend branch's complete tree was not safely verified in this audit.

Conditional candidates after tree-level review:

- Persistent user/auth models and password/token handling, if secure and better than the current prototype.
- Farmer and buyer profile persistence.
- Crop and market reference tables, if they retain the base API's normalized names and IDs can be mapped.
- Lot, demand, offer, and transaction persistence, if foreign keys and state transitions are correct.
- Repository/query patterns that can be adapted behind the existing API.
- Database initialization/migration tooling, if repeatable and non-destructive.

Every candidate must pass the API, data, security, and Chronos compatibility gates before adoption.

## 12. MERGE/ADAPT

- **Market data:** keep the base canonical loader and add a DB adapter or export view. Do not make the friend schema the direct Chronos input until validated.
- **Crops and markets:** use friend normalization/IDs only if the base string values and APMC resolution remain compatible.
- **Buyer demands:** replace the seed source only after the persisted demand API exposes the fields consumed by `match_buyers()`.
- **Lots:** map frontend fields (`crop`, `quantity`, `unit`, `grade`, `location`, `harvestDate`, `expectedPrice`, `status`) to backend columns with explicit units.
- **Offers:** preserve frontend statuses and add server-side ownership/status validation.
- **Transactions:** preserve the displayed lifecycle but make acceptance atomic and database-backed.
- **Authentication:** preserve `Authorization: Bearer` and role behavior; do not require auth for public market discovery unless intentionally versioned.
- **Error handling:** retain the base `{success: false, error: ...}` shape or update the frontend adapter in one controlled change.
- **Database timestamps:** use observation date for market data and separate created/updated timestamps for entities.

## 13. REJECT

Reject from the friend branch during future integration if present:

- Any non-Chronos forecast or model that replaces `ml/forecaster.py`.
- Any forecast endpoint that removes P10/P50/P90, evaluation, confidence, gap, or sale-window fields.
- Any schema that collapses distinct market/crop/date/variety/grade records.
- Any fallback that silently uses another market's prices.
- Unlabelled demo or seed data presented as official market data.
- Duplicate frontend dashboards or API clients.
- Hardcoded prices, match percentages, forecast values, or sale decisions.
- Unauthenticated ingestion or unrestricted bulk ingestion.
- Tables without ownership, foreign keys, uniqueness rules, or status-transition validation.
- Unreviewed migrations that drop, overwrite, or reinterpret existing historical data.
- Notifications, logistics, payments, or crop-quality claims unless a tested implementation and clear source of truth exist.

## 14. Database Changes Required

No database changes are authorized in this analysis phase.

For a future implementation, the minimum controlled change is:

1. Define a migration-owned relational schema for users, profiles, crops, markets, market observations, lots, demands, offers, and transactions.
2. Add a canonical market observation view/adapter exposing the ML fields required by `ml.data_loader.py`.
3. Define uniqueness for market + crop + date + variety + grade, with an explicit policy for source collisions.
4. Add indexes for crop/market/date and ownership/status queries.
5. Add foreign keys and deliberate delete behavior.
6. Add source, unit, observed date, created date, and freshness fields.
7. Import existing CSV data into a staging table first; compare counts, dates, prices, and duplicate keys before cutover.
8. Keep CSV fallback and rollback until Chronos forecasts match on a fixed test fixture.

## 15. Files That Will Need Changes During FUTURE Integration

These are candidates, not current edits:

- `backend/app.py`: application wiring and route registration.
- `ml/data_loader.py`: only if adding a DB source or adapter; preserve current CSV behavior.
- `ml/ingest.py`: only if ingestion persistence moves to a database.
- `ml/config.py`: database connection settings only; never replace Chronos settings.
- `frontend/js/api.js`: only for new authenticated business endpoints or compatibility adapters.
- `frontend/js/config.js`: only for new endpoint definitions.
- `frontend/js/dashboard.js`: replace local persistence with API calls incrementally.
- `frontend/js/price-forecast.js`: should remain unchanged unless the API adapter proves an unavoidable field mapping.
- `frontend/pages/farmer.html`: only for server-backed status/loading/error states.
- `frontend/pages/buyer.html`: only for server-backed demand/offer states.
- `requirements.txt`: only verified database/auth dependencies.
- `tests/test_ml_pipeline.py`: regression coverage for DB-backed canonical data.
- New migration/schema files: location and exact names depend on the verified friend implementation.
- New backend model/repository/service files: only after the friend tree and local conventions are verified.

Do not modify `ml/forecaster.py`, `ml/evaluator.py`, or `ml/decision_engine.py` as part of the first integration phase.

## 16. Integration Risks

- Replacing the CSV source can change market identity, date coverage, units, and forecast context.
- Database aggregation can introduce cross-market contamination.
- Duplicate imports can overweight dates and distort Chronos.
- Friend auth may conflict with the current frontend token helper.
- Frontend local state and database state can diverge during a partial migration.
- Offer acceptance can race without a database transaction.
- Seed buyer rows may be mistaken for verified buyers.
- CORS and ingestion exposure are security risks in the current base server.
- Chronos model load and large CSV load are expensive; a DB adapter must not create an even slower request path.
- Existing frontend static demo labels and local state can make a successful API integration look more complete than it is.
- Remote branch names can drift; the friend branch identity must be reconfirmed before implementation.

## 17. Testing Required After Integration

### Database and migration

- Fresh database initialization.
- Migration upgrade and rollback in a disposable database.
- PK/FK and cascade tests.
- Duplicate market observation tests.
- Null/invalid price/date/unit tests.
- Seed provenance tests.
- Query/index tests for crop, market, and date filters.

### ML compatibility

- Same canonical fixture from CSV and database adapter.
- Same market-specific filtered rows.
- Same date ordering and duplicate keys.
- Same `prepare_context()` length, gaps, winsorization, and tensor values.
- Same forecast response shape with `p10`, `p50`, `p90`.
- Same evaluation and sale-window fields.
- Sparse history and stale data behavior.

### Backend/API

- Auth registration/login/token rejection and role checks.
- Farmer/buyer ownership checks.
- Lot, demand, offer, and transaction validation.
- Atomic offer acceptance and idempotency.
- Existing forecast/market endpoint contract tests.
- Ingest authentication, payload size, duplicate, rejection, and source tests.
- Generic client errors without exception leakage.

### Frontend/end-to-end

- Dropdown cascade against the database-backed market source.
- Forecast table and quantile display.
- Sale-window rendering from API output, with no hardcoded action.
- Buyer match request field compatibility.
- Persisted lot/demand/offer/transaction workflows.
- Refresh/relogin behavior.
- Mobile farmer and buyer dashboard smoke tests.

## 18. Final Recommended Architecture

```text
                 relational business database
       users / profiles / lots / demands / offers / transactions
                              |
                     backend repositories/services
                              |
       market observation adapter with CSV fallback and provenance
                              |
                 existing ml.data_loader canonical frame
                              |
             existing Chronos + evaluator + decision engine
                              |
                    existing Flask forecast contract
                              |
                existing frontend API client and dashboards
```

The business database should own user and transaction state. The existing ML subsystem should own market-data normalization, forecasting, evaluation, uncertainty, and decision output until a tested replacement exists. The backend should compose the two through an explicit adapter, not by allowing a friend branch to overwrite the ML path.

## Future Integration Order

### PHASE 1: Database integration

First inspect and approve the friend schema without changing the base branch. Then create a staging/import path.

Candidate files to modify later:

- New migration/schema files.
- `backend/app/config/` or a new database configuration module.
- New database initialization script.
- `ml/data_loader.py` only for an opt-in database adapter.
- `tests/` database compatibility tests.

Exit gate: imported market observations reproduce the base canonical fixture and no forecast regression is observed.

### PHASE 2: Backend models/repositories/services

Add only approved user, profile, lot, demand, offer, transaction, and market repositories/services.

Candidate files to modify later:

- New `backend/app/models/` files.
- New `backend/app/repositories/` files.
- New `backend/app/services/` files.
- Auth middleware/config files if the friend auth passes review.
- `backend/app.py` wiring.

Exit gate: unit tests prove ownership, validation, foreign keys, and state transitions.

### PHASE 3: API integration

Expose durable business endpoints while preserving all existing forecast and market endpoints.

Candidate files to modify later:

- `backend/app.py` or new route modules.
- New controllers/route modules.
- `frontend/js/api.js` for new calls.
- `frontend/js/config.js` for new endpoint constants.
- API contract tests.

Exit gate: current frontend forecast calls remain byte/field compatible and new endpoints have explicit contracts.

### PHASE 4: Connect backend/database to existing Chronos pipeline

Make the DB adapter an opt-in source, compare against CSV, and only then make it the default source.

Candidate files to modify later:

- `ml/data_loader.py`.
- `ml/ingest.py`.
- `ml/config.py` for connection configuration only.
- `backend/app.py` data-store initialization.
- ML regression tests.

Do not modify `ml/forecaster.py`, `ml/evaluator.py`, or `ml/decision_engine.py` unless a test demonstrates a critical defect.

### PHASE 5: Connect existing frontend

Replace local persistence incrementally for lots, demands, offers, and transactions. Leave forecast UI wiring intact unless an adapter is required.

Candidate files to modify later:

- `frontend/js/api.js`.
- `frontend/js/dashboard.js`.
- `frontend/js/config.js`.
- `frontend/pages/farmer.html`.
- `frontend/pages/buyer.html`.
- Related CSS only for loading/error states.

Exit gate: refresh, login, role ownership, and forecast display all work together.

### PHASE 6: Testing

Run database, backend, ML, frontend contract, security, and regression suites. Add fixed fixtures and compare CSV versus DB outputs.

Candidate files to modify later:

- `tests/`.
- New backend API tests.
- New database migration tests.
- New frontend contract/smoke tests.

### PHASE 7: Full end-to-end verification

Verify:

```text
user login
  -> farmer lot / buyer demand
  -> persisted market data selection
  -> existing Chronos forecast
  -> P10/P50/P90 and sale-window response
  -> buyer matching
  -> offer
  -> transaction lifecycle
```

Only after all gates pass should the database source become the default and CSV fallback be reconsidered.

## Final Verdict

1. **What from my frontend branch must NEVER be replaced?**  The Chronos model loading, data loader, preprocessing, P10/P50/P90 forecast output, evaluator, sale-window decision engine, buyer matcher, forecast API contract, and working forecast frontend.
2. **What exactly should we take from the friend branch?**  Only verified, tested persistence and backend business functionality: authentication, profiles, lots, demands, offers, transactions, and database tooling if those implementations pass review.
3. **What exactly should we reject?**  Any friend forecast replacement, unverified schema, duplicate API/client, hardcoded/demo data presented as live, unsafe ingestion, and any component without ownership/constraints/tests.
4. **Which database tables should come from friend?**  None are approved yet. User/profile/lot/demand/offer/transaction tables are conditional candidates after the friend tree is verified.
5. **Which database tables should remain mine?**  The base market-data/forecast input semantics and historical CSV data remain the source of truth for Chronos during migration. The base has no verified relational business tables.
6. **Which tables need merging?**  Crops, markets, and market observations need an adapter/merge strategy if the friend branch supplies normalized relational entities. Lots and demands need mapping to the existing frontend and matcher fields.
7. **Can friend's database work with my Chronos pipeline?**  Yes, conditionally, if it produces the base canonical observation contract and preserves market/date/variety/grade uniqueness, units, freshness, and provenance. It cannot replace Chronos directly.
8. **What backend pieces should be integrated?**  Verified auth, profile, lot, buyer-demand, offer, transaction, repository, validation, and migration components, added around the existing ML backend.
9. **What should remain untouched?**  `ml/forecaster.py`, `ml/data_loader.py` behavior, `ml/evaluator.py`, `ml/decision_engine.py`, `ml/buyer_matcher.py`, P10/P50/P90 fields, existing forecast frontend, and current market-selection contract.
10. **What is the safest integration order?**  Database staging and compatibility tests, backend models/repositories/services, additive APIs, opt-in DB-to-Chronos adapter, incremental frontend persistence, full tests, then end-to-end verification.

**Current decision:** analysis complete; integration intentionally not performed. The only unresolved blocker is obtaining a safe, read-only tree/diff inventory of the friend branch so conditional candidates can be converted into exact `TAKE`, `MERGE/ADAPT`, or `REJECT` decisions before implementation.
