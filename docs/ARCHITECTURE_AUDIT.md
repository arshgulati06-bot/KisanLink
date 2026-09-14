# KisanLink Architecture Audit

**Date:** 2026-09-10  
**Scope:** Full inspection of ML, backend, frontend, tests, docs, git working tree.  
**Rule:** This document records the current implementation and its verified limitations. It is not a historical snapshot.

---

## 1. What is currently working

- Combined loader for three real CSVs (`Agriculture_price_dataset.csv`, `2022.csv`, `2026.csv`) with schema rename, whitespace strip, APMC suffix strip, title-case, date/price coercion.
- Market filtering is market-specific (no silent district/state fallback).
- Fuzzy market resolution only when exactly one substring candidate exists.
- Gap detection (`MAX_GAP_DAYS=365`) prefers the most recent continuous segment with enough observations.
- IQR winsorization with IQR=0 guard (`lo=0` when IQR is 0; upper fence uses `max(k*IQR, k*Q3)`).
- Chronos (`amazon/chronos-t5-tiny`) produces 7-day forecasts with sample quantiles (P10/P50/P90).
- Holdout evaluation (MAE/RMSE/MAPE) plus naive and MA7 baselines.
- Flask endpoints for commodities/states/districts/markets, forecast, market-compare, market-intel, sale-window, buyer-demands, buyer-match, ingest status/update.
- Farmer Price Outlook UI: cascading dropdowns from the API; forecast table and sale-window chip from `/api/forecast`.
- View Matches on lot cards calls `/api/buyer-match` with the current selection context.
- Existing `tests/test_ml_pipeline.py` covers gaps, winsorization, APMC, Pimpalgaon regression, forecast shape, evaluation.

## 2. Configuration and seed data

- Chronos model id, device, horizon, context length, min records (legitimate config, not market prices).
- Decision-engine thresholds: ₹50/QTL min wait benefit; uncertainty bands 0.15 / 0.30.
- Buyer matcher weights (35/20/20/15/10) and a small neighbour-state map.
- Chronos model id, device, horizon, context length, minimum records, and decision thresholds are configuration.
- `ml/data/buyers/demands.json` is a clearly labelled local seed buyer-demand source, not a live buyer marketplace.
- Prototype profile/lot/offer state remains local UI state and is not presented as live mandi data.

## 3. What is demo / placeholder data

- Landing-page explanatory copy and role/demo modal are product-prototype UI, not mandi data.
- Buyer-demand rows are local seed requirements and are labelled through the API provenance note.
- Notifications module: demo items.
- Chat assistant: explicitly not connected.
- Crop quality: placeholder result after a fake delay.
- Ingest status correctly sets `live_api_connected: false`, but forecast responses still label source as “data.gov.in / AGMARKNET” even though only local CSVs are loaded.
- Buyer demands API note says “real buyer integration pending” while still serving seed rows as if they were platform-registered.

## 4. What is genuinely data-driven

- Historical prices and geography lists from the three CSVs.
- Chronos median/quantile forecasts from the prepared context tensor.
- Sale-window action/reason from forecast vs latest historical price.
- Market-compare latest modal prices grouped from the combined frame.
- Buyer **scores** (when the matcher runs) are computed from lot vs demand fields — the **inputs** were seed/demo, not live APIs.
- Gap/outlier metadata from the actual series.

## 5. Backend endpoints (audit-time)

| Method | Path | Data source |
|--------|------|-------------|
| GET | `/api/commodities` | Combined CSV frame |
| GET | `/api/states` | Combined CSV frame |
| GET | `/api/districts` | Combined CSV frame |
| GET | `/api/markets` | Combined CSV frame |
| POST | `/api/forecast` | Chronos + decision engine |
| GET | `/api/market-compare` | Combined CSV frame |
| GET | `/api/market-intel` | Combined CSV frame + prepare_context |
| POST | `/api/sale-window` | Chronos + decision engine |
| GET | `/api/buyer-demands` | In-process seed list |
| POST | `/api/buyer-match` | Matcher vs seed list |
| GET | `/api/buyer-matches` | Query-form matcher alias |
| GET | `/api/ingest/status` | In-memory metadata |
| POST | `/api/ingest/update` | In-memory append only |
| GET | `/`, `/<path>` | Static frontend |

No auth, lots, offers, or quality endpoints exist.

## 6. ML pipeline

1. `load_combined_data()` → concat three CSVs → normalize → drop exact duplicates → sort by date.  
2. `get_market_data()` → commodity+state+district+market filter.  
3. `prepare_context()` → daily median → gap truncate → winsorize → last 150 points → Chronos tensor.  
4. `forecast_with_quantiles()` → Chronos samples → P10/P50/P90, clamp ≥ 0.  
5. `evaluate_model()` → holdout last 7 days if ≥ 21 points.  
6. `recommend_sale_window()` → risk-adjusted wait vs sell now.

CLI: `python -m ml.run_forecast`. Model loaded once in Flask process.

## 7. Data flow (CSV/API → UI)

```
ml/data/*.csv  ──►  load_combined_data  ──►  in-memory _df (Flask)
                                              │
POST /api/ingest/update  ──►  validate/normalize/dedup  ──►  concat _df
                                              │  persisted to `ml/data/ingested/records.csv`
                                              ▼
                         get_market_data → prepare_context → Chronos
                                              ▼
                         /api/forecast JSON → price-forecast.js
                                              ▼
                         kl:forecastReady → Best Action / Recommendations
```

No official live API client. No credentials in repo.

## 8. Missing functionality

- Shared multi-worker ingest coordination; each Flask worker owns its in-memory frame.
- Official mandi API adapter gated on real env config.
- Ingest auth, payload-size limit, rejection log file.
- Precomputed lowercase filter columns / faster lookup.
- Frontend ingest-status / “data is old, not today’s price” banner.
- Empty/error UX on landing page (shows fake prices instead).
- Crop-quality model, chat backend, maps/distance, auth.

## 9. Duplicate / redundant code

- `forecast_prices` wraps `forecast_with_quantiles`.
- `/api/sale-window` duplicates forecast path.
- Column rename maps copied in loader, cleaner, and ingest handler.
- APMC regex duplicated in ingest loop (`import re` inside loop).
- Step4 and price-forecast both bind `#mc-fetch-btn`.
- Seed buyers duplicated in `app.py`, `config.js`, and diagnostic scripts.
- `.bak` copies of `app.py`, `config.py`, `data_loader.py`, `run_forecast.py`.

## 10. Potential bugs

- Manual comparison ownership is centralized in `price-forecast.js`.
- Market-compare JS rows use 5 `<td>` vs 6 `<th>`; market-intel JS vs 8-column header mismatch.
- `dashboard.js` buyer-card HTML: missing `>` before `₹` in offered-rate span.
- Ingest dedup: `_df[dedup_key].apply(..., axis=1)` on 5.8M rows — extremely slow / may timeout.
- Ingest does not reject absurd prices, missing State values that are the string `"nan"`, or oversized payloads.
- Exceptions returned as `str(e)` to clients (stack-ish internals).
- `dayfirst=False` on mixed date formats can swap day/month on some rows.
- Forecast dates are calendar +1 from last observation, not next trading/mandi day.
- `CORS(app)` + `host=0.0.0.0` with open ingest.
- Flask loads Chronos and 5.8M rows at **import** time — tests and tooling pay full cost.
- `config.js` `REQUEST_TIMEOUT_MS: 8000` vs forecast needing 60–90s (`api.js` overrides some calls).
- Decision engine day-0 uses latest price, not day-1 forecast; WAIT requires `net_benefit >= 50` **and** best risk-adj — fine, but high-uncertainty wait can still win if benefit is large.
- `_grade_score` default 50 for unknown grades.

## 11. Security problems

- `POST /api/ingest/update` unauthenticated; anyone who can reach the port can inject prices and poison forecasts.
- No `MAX_CONTENT_LENGTH`.
- No numeric range / injection of unexpected columns (extra keys dropped only at append keep-list).
- Error responses may leak exception text.
- CORS allows all origins.
- Auth token stored in localStorage (unused by ML API).
- No secrets file; good. Binding `0.0.0.0` exposes ingest on LAN.

## 12. Performance problems

- Three full CSV reads (~409MB + 62MB + 55MB) per process start; no parquet/pickle cache.
- Per-request `str.lower()` scans on millions of rows for dropdowns.
- Ingest dedup `DataFrame.apply` over entire `_df`.
- Forecast **and** evaluation each call Chronos (two inferences per `/api/forecast`).
- Tests/diagnostics reload 5.8M rows if they do not share a fixture (test_ml_pipeline is module-scoped; diagnostics load again).
- No index on (commodity, state, district, market).

## 13. What should be deleted

- `backend/app.py.bak`, `ml/config.py.bak`, `ml/data_loader.py.bak`, `ml/run_forecast.py.bak`.
- Frontend demo market arrays and static fake APMC prices used as if live.
- Duplicate ingest logic inside `app.py` after extracting `ml/ingest.py`.
- Empty `databse/` typo directory if unused.

## 14. What should be added

- `ml/ingest.py`: normalize, validate, dedup, persist, log, latest-date.
- Combined cache + in-memory store with lowercase filter columns.
- Optional data.gov.in fetch **only** when `DATA_GOV_API_KEY` + resource id are set.
- Ingest token + size limits; generic client errors.
- Buyer demands file (seed, labelled) scored by matcher — no hardcoded 92%.
- Tests for ingest, API, sparse/missing markets, hardcode audit, decision engine, buyer match, market compare.
- Docs: DATA_INGESTION.md, FORECASTING.md; this audit updated after remediation.
- Farmer UI: freshness, P10/P50/P90, gaps, confidence, API errors; strip demo overlays.

## 15. Exact recommended architecture

```
                    ┌─────────────────────────────────────┐
                    │  Official source (optional)         │
                    │  DATA_GOV_API_KEY + RESOURCE_ID     │
                    │  ml/ingest.py::fetch_official()     │
                    └──────────────────┬──────────────────┘
                                       │ only if configured
ml/data/2022.csv                       ▼
ml/data/Agriculture_price_dataset.csv ► load_combined_data()
ml/data/2026.csv                       │  normalize + APMC strip
ml/data/ingested/records.parquet ─────►│  concat + dedup
                                       │  write _cache/combined.pkl
                                       ▼
                              MandiStore (in process)
                              lowercase columns, latest_date
                                       │
          GET lists / compare / intel ─┤
          POST forecast ─ Chronos cache┤
          POST ingest ─ validate/log ──┘ persist ingested + refresh store
                                       │
                              Flask JSON (no fake prices)
                                       ▼
                    farmer.html ← price-forecast.js (no step4 demo overwrite)
```

**Daily update path:** scheduler or operator POSTs JSON records to `/api/ingest/update` (Bearer token if `KISANLINK_INGEST_TOKEN` is set), or `fetch_from_source: true` when official API env is present. Forecasting always reads the live store, which includes newly ingested rows.

---

## Remediation status (same change set)

See `docs/DATA_INGESTION.md` and `docs/FORECASTING.md` for the implementation after fixes. Residual limitations are listed in the final engineering report, not as pretend live APIs.
