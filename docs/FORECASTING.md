# Forecasting (actual implementation)

## Model

Amazon Chronos `amazon/chronos-t5-tiny` on CPU (`ml/config.py`). The Flask process loads the pipeline once via `create_app()`.

## Series construction (`ml/data_loader.py`)

1. Filter **only** the requested commodity + state + district + market (`get_market_data`). No district/state fallback. `Pimpalgaon APMC` resolves to `Pimpalgaon`.
2. Daily median of `Modal_Price`.
3. If a gap exceeds `MAX_GAP_DAYS` (365), keep the most recent continuous segment with at least `MIN_RECORDS` (14) points.
4. Winsorize context with `OUTLIER_IQR_K=5`. When IQR is 0, the lower fence is 0 so a flat series is not collapsed; the upper fence uses `max(k*IQR, k*Q3)`.
5. Last `MAX_CONTEXT_LENGTH` (150) points become the Chronos tensor.

Raw CSV rows are not rewritten.

## Forecast (`ml/forecaster.py`)

`pipeline.predict` draws `FORECAST_SAMPLES` (20) trajectories. Reported values are P10 / P50 / P90, clamped at 0. Model output is never replaced with a hardcoded price.

`POST /api/forecast` also runs holdout evaluation when ≥ 21 daily points exist (`ml/evaluator.py`: MAE, RMSE, MAPE vs naive and MA7).

## Decision (`ml/decision_engine.py`)

`recommend_sale_window` compares each forecast day to the **latest historical modal price**, subtracts optional storage cost, and penalizes wide P90–P10 bands. Actions are `SELL_NOW` or `WAIT_N_DAYS` with a written reason. The frontend must display this payload; it must not hardcode SELL NOW.

## API payload (abridged)

- `latest_price`, `latest_actual_date`, `date_range`
- `forecast[].p10/p50/p90` (aliases `price_low` / `price` / `price_high`)
- `evaluation` or null
- `confidence` (Good/Moderate/Low, days since last record, `stale_data`)
- `gap_info`, `n_winsorized`, `sale_window`

Confidence notes state when data is old. The UI must not present the last CSV date as a live “today” tick.

## CLI

`python -m ml.run_forecast --commodity Tomato --state Maharashtra --district Nashik --market Pimpalgaon`

Uses the same combined loader (unless `--csv` points at a single file).
