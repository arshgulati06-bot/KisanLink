# Data ingestion (actual implementation)

KisanLink does **not** claim a live government API unless `DATA_GOV_API_KEY` and `DATA_GOV_RESOURCE_ID` are set in the environment.

## Historical source (always used)

`ml.data_loader.load_combined_data()` reads:

- `ml/data/Agriculture_price_dataset.csv`
- `ml/data/2022.csv`
- `ml/data/2026.csv`

Schemas are renamed to `State, District, Market, Commodity, Variety, Grade, Date, Min_Price, Max_Price, Modal_Price`. Trailing ` APMC` is stripped from market names; strings are title-cased; dates and prices are coerced; invalid date/price rows are dropped; exact duplicates are removed.

A pickle cache is written to `ml/data/_cache/combined.pkl` keyed by source file mtimes/sizes so processes do not re-parse millions of CSV rows on every start. Lowercase filter columns (`_commodity_l`, `_state_l`, `_district_l`, `_market_l`) are attached for request filtering.

Persisted ingest rows in `ml/data/ingested/records.csv` (if present) are concatenated before caching.

## Daily / incremental ingest

`POST /api/ingest/update` (`ml/ingest.py`):

1. Optional `Authorization: Bearer <KISANLINK_INGEST_TOKEN>` when that env var is set.
2. Payload size capped (`KISANLINK_INGEST_MAX_BYTES`, default 2 MiB) and record count capped (`KISANLINK_INGEST_MAX_RECORDS`, default 2000).
3. Accepts canonical names or aliases (`Arrival_Date`, `Market Name`, …).
4. Rejects missing geography, unparseable dates, non-positive or absurd modal prices (`> 10_000_000`), and path-like strings.
5. Deduplicates on state|district|market|commodity|date|variety|grade (vectorized keys, not row-wise `apply` on 5.8M rows).
6. Appends new rows to `ml/data/ingested/records.csv` and to the in-memory store used by forecast endpoints.
7. Logs rejections to `ml/data/ingested/ingest.log`.
8. Returns `added`, `duplicates_skipped`, `invalid_skipped`, `reject_reasons`, `latest_date_in_dataset`.

Repeating the same POST is safe: duplicates are skipped.

`GET /api/ingest/status` reports record count, latest date, whether an official API is configured, and that stale history is not “today’s price”.

## Optional official fetch

If both `DATA_GOV_API_KEY` and `DATA_GOV_RESOURCE_ID` are set, `POST /api/ingest/update` with `{"fetch_from_source": true}` calls `https://api.data.gov.in/resource/<id>`. If they are not set, the handler returns an error and `live_api_connected` remains false. No fake success payload is generated.

## How the frontend sees new data

The Flask process holds the combined frame. After a successful ingest, list/forecast/compare endpoints read the updated frame immediately. A process restart reloads CSVs + cache invalidation + `ingested/records.csv`.
