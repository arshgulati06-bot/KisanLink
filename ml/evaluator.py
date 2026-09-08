"""
KisanLink ML Pipeline — Model Evaluation
==========================================
Backtesting evaluation using holdout split on historical data.
Metrics: MAE, RMSE, MAPE.
"""

import numpy as np
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error

from . import config


# =============================================================================
# evaluate_model
# =============================================================================

def evaluate_model(pipeline, prices, test_size=None):
    """
    Evaluate the Chronos model using a holdout backtesting approach.

    Splits the historical price series into train and test.
    Uses the train portion as context, forecasts `test_size` steps,
    and compares against the actual held-out prices.

    Parameters
    ----------
    pipeline : ChronosPipeline
        Loaded Chronos model.
    prices : np.ndarray
        Full daily price series (chronologically ordered).
    test_size : int, optional
        Number of days to hold out for testing.
        Defaults to config.EVAL_TEST_SIZE.

    Returns
    -------
    dict or None
        If enough data exists, returns dict with keys:
            "mae"       : float
            "rmse"      : float
            "mape"      : float (percentage)
            "actuals"   : np.ndarray
            "predicted" : np.ndarray
        Returns None if insufficient data for evaluation.
    """
    if test_size is None:
        test_size = config.EVAL_TEST_SIZE

    if len(prices) < config.MIN_EVAL_RECORDS:
        return None

    # Split into train and test
    train_prices = prices[:-test_size]
    actual_prices = prices[-test_size:]

    # Build context from training portion
    eval_context = torch.tensor(
        train_prices,
        dtype=torch.float32,
    ).unsqueeze(0)

    # Forecast
    eval_forecast = pipeline.predict(
        eval_context,
        prediction_length=test_size,
    )

    predicted_prices = eval_forecast[0].median(dim=0).values.numpy()
    predicted_prices = np.maximum(predicted_prices, 0)

    # Compute metrics
    mae = mean_absolute_error(actual_prices, predicted_prices)

    rmse = np.sqrt(
        mean_squared_error(actual_prices, predicted_prices)
    )

    # MAPE — guard against division by zero
    nonzero_mask = actual_prices != 0
    if nonzero_mask.any():
        mape = np.mean(
            np.abs(
                (actual_prices[nonzero_mask] - predicted_prices[nonzero_mask])
                / actual_prices[nonzero_mask]
            )
        ) * 100
    else:
        mape = float("inf")

    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "actuals": actual_prices,
        "predicted": predicted_prices,
    }
