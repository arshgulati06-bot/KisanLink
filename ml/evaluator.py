"""
KisanLink ML Pipeline — Model Evaluation
==========================================
Backtesting evaluation using holdout split on historical data.

Metrics for Chronos:
  - MAE, RMSE, MAPE

Baseline models for comparison:
  - Naive (last-value): predict last known price for all test days
  - MA7 (7-day moving average): predict rolling mean of last 7 train days
"""

import numpy as np
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error

from . import config


# =============================================================================
# _compute_metrics
# =============================================================================

def _compute_metrics(actuals, predicted):
    """
    Compute MAE, RMSE, MAPE for a pair of actual/predicted arrays.
    Returns dict with mae, rmse, mape (float). mape is a percentage.
    """
    actuals   = np.asarray(actuals,   dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    mae  = float(mean_absolute_error(actuals, predicted))
    rmse = float(np.sqrt(mean_squared_error(actuals, predicted)))

    nonzero = actuals != 0
    if nonzero.any():
        mape = float(
            np.mean(np.abs((actuals[nonzero] - predicted[nonzero])
                           / actuals[nonzero])) * 100
        )
    else:
        mape = float("inf")

    return {"mae": mae, "rmse": rmse, "mape": mape}


# =============================================================================
# evaluate_model
# =============================================================================

def evaluate_model(pipeline, prices, test_size=None):
    """
    Evaluate Chronos plus two simple baselines using holdout backtesting.

    The function splits the historical price series into train and test,
    runs Chronos on the train context, then evaluates both Chronos and
    two naive baselines against the held-out test window.

    Baselines:
      - Naive: predict last train price for every test day
      - MA7:   predict the 7-day rolling mean of the last 7 train prices

    Parameters
    ----------
    pipeline : ChronosPipeline
    prices : np.ndarray
        Full cleaned daily price series (chronological order).
    test_size : int, optional
        Number of test days. Defaults to config.EVAL_TEST_SIZE (= 7).

    Returns
    -------
    dict or None
        If sufficient data: dict with keys:
            "mae", "rmse", "mape"       — Chronos metrics
            "actuals"                   — np.ndarray of test actuals
            "predicted"                 — np.ndarray of Chronos predictions
            "baseline_naive"            — {"mae", "rmse", "mape"}
            "baseline_ma7"              — {"mae", "rmse", "mape"}
            "chronos_vs_naive_pct"      — % improvement over naive (negative = worse)
        Returns None if < config.MIN_EVAL_RECORDS available.
    """
    if test_size is None:
        test_size = config.EVAL_TEST_SIZE

    if len(prices) < config.MIN_EVAL_RECORDS:
        return None

    train_prices  = prices[:-test_size]
    actual_prices = prices[-test_size:]

    # ── Chronos evaluation ──
    eval_context = torch.tensor(
        train_prices, dtype=torch.float32
    ).unsqueeze(0)

    eval_forecast = pipeline.predict(
        eval_context,
        prediction_length=test_size,
    )
    predicted_prices = eval_forecast[0].median(dim=0).values.numpy()
    predicted_prices = np.maximum(predicted_prices, 0)

    chronos_metrics = _compute_metrics(actual_prices, predicted_prices)

    # ── Naive baseline (last-value) ──
    naive_pred = np.full(test_size, train_prices[-1])
    naive_metrics = _compute_metrics(actual_prices, naive_pred)

    # ── MA7 baseline ──
    ma7_window = train_prices[-7:] if len(train_prices) >= 7 else train_prices
    ma7_val    = float(np.mean(ma7_window))
    ma7_pred   = np.full(test_size, ma7_val)
    ma7_metrics = _compute_metrics(actual_prices, ma7_pred)

    # ── Relative improvement over naive ──
    if naive_metrics["mae"] > 0:
        vs_naive = (naive_metrics["mae"] - chronos_metrics["mae"]) / naive_metrics["mae"] * 100
    else:
        vs_naive = 0.0

    return {
        "mae":                   chronos_metrics["mae"],
        "rmse":                  chronos_metrics["rmse"],
        "mape":                  chronos_metrics["mape"],
        "actuals":               actual_prices,
        "predicted":             predicted_prices,
        "baseline_naive":        naive_metrics,
        "baseline_ma7":          ma7_metrics,
        "chronos_vs_naive_pct":  round(vs_naive, 1),
    }
