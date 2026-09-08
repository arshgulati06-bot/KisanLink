"""
KisanLink ML Pipeline — Chronos Forecaster
============================================
Wrapper around the pretrained Amazon Chronos model
for generating mandi price forecasts.
"""

import torch
import numpy as np
from chronos import ChronosPipeline

from . import config


# =============================================================================
# load_model
# =============================================================================

def load_model(model_name=None, device=None):
    """
    Load the pretrained Chronos pipeline.

    Parameters
    ----------
    model_name : str, optional
        HuggingFace model identifier. Defaults to config.MODEL_NAME.
    device : str, optional
        Device to run on ("cpu" or "cuda"). Defaults to config.MODEL_DEVICE.

    Returns
    -------
    ChronosPipeline
        Ready-to-use Chronos forecasting pipeline.
    """
    if model_name is None:
        model_name = config.MODEL_NAME
    if device is None:
        device = config.MODEL_DEVICE

    pipeline = ChronosPipeline.from_pretrained(
        model_name,
        device_map=device,
        dtype=torch.float32,
    )
    return pipeline


# =============================================================================
# forecast_prices
# =============================================================================

def forecast_prices(pipeline, context_tensor, prediction_length=None):
    """
    Generate a price forecast using the Chronos model.

    Parameters
    ----------
    pipeline : ChronosPipeline
        Loaded Chronos model from load_model().
    context_tensor : torch.Tensor
        Historical price context, shape (1, context_length).
    prediction_length : int, optional
        Number of days to forecast. Defaults to config.FORECAST_HORIZON.

    Returns
    -------
    np.ndarray
        Array of forecast values (length = prediction_length).
        Negative values are clamped to 0.
    """
    if prediction_length is None:
        prediction_length = config.FORECAST_HORIZON

    forecast = pipeline.predict(
        context_tensor,
        prediction_length=prediction_length,
    )

    # Extract median of predicted quantiles
    median_forecast = forecast[0].median(dim=0).values.numpy()

    # Clamp negatives to zero (prices can't be negative)
    median_forecast = np.maximum(median_forecast, 0)

    return median_forecast
