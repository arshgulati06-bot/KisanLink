"""
KisanLink ML Pipeline — Chronos Forecaster
============================================
Wrapper around the pretrained Amazon Chronos model
for generating mandi price forecasts.

Returns median forecast plus q10/q90 quantile bounds for
uncertainty display in the frontend.
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

def forecast_prices(pipeline, context_tensor, prediction_length=None,
                    num_samples=None):
    """
    Generate a price forecast using the Chronos model.

    Returns the median forecast (backward-compatible) as an np.ndarray.
    Use forecast_with_quantiles() to also get uncertainty bounds.

    Parameters
    ----------
    pipeline : ChronosPipeline
        Loaded Chronos model from load_model().
    context_tensor : torch.Tensor
        Historical price context, shape (1, context_length).
    prediction_length : int, optional
        Number of days to forecast. Defaults to config.FORECAST_HORIZON.
    num_samples : int, optional
        Number of Monte-Carlo samples for uncertainty. Default: config.FORECAST_SAMPLES.

    Returns
    -------
    np.ndarray
        Array of median forecast values (length = prediction_length).
        Negative values are clamped to 0.
    """
    result = forecast_with_quantiles(
        pipeline, context_tensor,
        prediction_length=prediction_length,
        num_samples=num_samples,
    )
    return result["median"]


# =============================================================================
# forecast_with_quantiles
# =============================================================================

def forecast_with_quantiles(pipeline, context_tensor, prediction_length=None,
                             num_samples=None):
    """
    Generate a price forecast with predictive uncertainty bands.

    Chronos generates `num_samples` sample trajectories internally.
    We extract:
      - q10 (10th percentile) → optimistic lower bound
      - q50 (median)         → point forecast
      - q90 (90th percentile) → optimistic upper bound

    Parameters
    ----------
    pipeline : ChronosPipeline
    context_tensor : torch.Tensor — shape (1, context_length)
    prediction_length : int, optional
    num_samples : int, optional — number of Monte-Carlo samples

    Returns
    -------
    dict with keys:
        "median"  : np.ndarray — shape (prediction_length,), clamped >= 0
        "low"     : np.ndarray — q10 bound, clamped >= 0
        "high"    : np.ndarray — q90 bound, clamped >= 0
        "samples" : int        — num_samples used
    """
    if prediction_length is None:
        prediction_length = config.FORECAST_HORIZON
    if num_samples is None:
        num_samples = getattr(config, "FORECAST_SAMPLES", 20)

    # Chronos predict() returns shape (num_series, num_samples, prediction_length)
    forecast = pipeline.predict(
        context_tensor,
        prediction_length=prediction_length,
        num_samples=num_samples,
    )

    # forecast[0] is shape (num_samples, prediction_length)
    samples = forecast[0]  # torch.Tensor

    # Convert to numpy for percentile computation
    samples_np = samples.float().numpy()  # (num_samples, prediction_length)

    median = np.percentile(samples_np, 50, axis=0)
    low    = np.percentile(samples_np, 10, axis=0)
    high   = np.percentile(samples_np, 90, axis=0)

    # Clamp negatives (prices can't be negative)
    median = np.maximum(median, 0.0)
    low    = np.maximum(low,    0.0)
    high   = np.maximum(high,   0.0)

    return {
        "median":  median,
        "low":     low,
        "high":    high,
        "p10":     low,
        "p50":     median,
        "p90":     high,
        "samples": num_samples,
    }
