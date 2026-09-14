"""
KisanLink ML Pipeline — Sale-Window Decision Engine
=====================================================
Data-driven, explainable recommendation for WHEN to sell.

Logic:
  For each candidate day d = 0..7 (0 = sell today):
    expected_gain    = (forecast_median[d] - latest_price) * quantity_qtl
    storage_cost     = storage_cost_per_day * d * quantity_qtl
    net_benefit      = expected_gain - storage_cost
    uncertainty      = (high[d] - low[d]) / median[d]  (relative width)
    risk_adj_benefit = net_benefit * (1 - 0.5 * uncertainty_penalty)

  Pick the day with highest risk-adjusted net_benefit.
  If no future day beats SELL_NOW by a meaningful margin, recommend SELL_NOW.
  If data quality is low (high uncertainty), be conservative.

This engine only uses real forecast values and real historical prices.
It does NOT hardcode any recommendation.
"""

import numpy as np
from typing import Optional


# ---------------------------------------------------------------------------
# Constants (all tunable — not hardcoded per commodity)
# ---------------------------------------------------------------------------
_MIN_BENEFIT_PER_QTL  = 50.0   # ₹/QTL — must beat this to recommend waiting
_HIGH_UNCERTAINTY_THR = 0.30   # relative IQR width above which we flag "high uncertainty"
_MED_UNCERTAINTY_THR  = 0.15


def _uncertainty_label(rel_width: float) -> str:
    if rel_width >= _HIGH_UNCERTAINTY_THR:
        return "High"
    elif rel_width >= _MED_UNCERTAINTY_THR:
        return "Medium"
    return "Low"


# =============================================================================
# recommend_sale_window
# =============================================================================

def recommend_sale_window(
    forecast_median:        np.ndarray,   # shape (7,) — ₹/QTL
    forecast_low:           np.ndarray,   # shape (7,) — q10
    forecast_high:          np.ndarray,   # shape (7,) — q90
    latest_price:           float,        # ₹/QTL — most recent market price
    quantity_qtl:           float = 10.0, # farmer's lot size in quintals
    storage_cost_per_day:   float = 0.0,  # ₹/QTL/day
    min_benefit_per_qtl:    float = _MIN_BENEFIT_PER_QTL,
    context_n_obs:          Optional[int] = None,  # for low-data warning
) -> dict:
    """
    Recommend whether to sell now or wait, with full reasoning.

    Parameters
    ----------
    forecast_median : np.ndarray, shape (7,)
    forecast_low    : np.ndarray, shape (7,)  — q10 lower bound
    forecast_high   : np.ndarray, shape (7,)  — q90 upper bound
    latest_price    : float
    quantity_qtl    : float — lot size in QTL
    storage_cost_per_day : float — ₹ per QTL per day in storage
    min_benefit_per_qtl  : float — minimum net gain to justify waiting
    context_n_obs        : int or None — how many historical obs were used

    Returns
    -------
    dict with keys:
        "action"          : "SELL_NOW" | "WAIT_N_DAYS"
        "wait_days"       : int (0 if SELL_NOW)
        "expected_price"  : float — forecast price on recommended day
        "expected_gain_per_qtl" : float — ₹/QTL gain vs latest price
        "storage_cost_total"    : float — total ₹ storage cost
        "net_benefit_per_qtl"   : float — after storage
        "uncertainty"     : "High"|"Medium"|"Low"
        "reason"          : str — human-readable explanation
        "day_analysis"    : list of dicts — per-day breakdown
        "data_quality_note": str or None
    """
    n = len(forecast_median)
    assert n == len(forecast_low) == len(forecast_high), "Forecast arrays must be same length"

    day_analysis = []
    best_risk_adj = -np.inf
    best_day      = 0   # 0 = sell today

    # Day 0 = SELL NOW (no waiting)
    day_analysis.append({
        "day":               0,
        "label":             "Today (Sell Now)",
        "forecast_price":    float(latest_price),
        "gain_per_qtl":      0.0,
        "storage_cost":      0.0,
        "net_benefit":       0.0,
        "uncertainty":       "N/A",
        "risk_adj_benefit":  0.0,
    })

    for d in range(n):
        day_num          = d + 1
        fc_med           = float(forecast_median[d])
        fc_lo            = float(forecast_low[d])
        fc_hi            = float(forecast_high[d])

        gain_per_qtl     = fc_med - latest_price
        storage_cost_qtl = storage_cost_per_day * day_num
        net_benefit_qtl  = gain_per_qtl - storage_cost_qtl

        # Relative uncertainty (width of 80% prediction interval / median)
        if fc_med > 0:
            rel_width = (fc_hi - fc_lo) / fc_med
        else:
            rel_width = 1.0

        uncertainty = _uncertainty_label(rel_width)
        unc_penalty = rel_width * 0.5   # dampen risky days

        risk_adj = net_benefit_qtl * (1.0 - min(unc_penalty, 0.9))

        if risk_adj > best_risk_adj and net_benefit_qtl >= min_benefit_per_qtl:
            best_risk_adj = risk_adj
            best_day      = day_num

        day_analysis.append({
            "day":               day_num,
            "label":             f"Day {day_num}",
            "forecast_price":    round(fc_med, 2),
            "gain_per_qtl":      round(gain_per_qtl, 2),
            "storage_cost":      round(storage_cost_qtl, 2),
            "net_benefit":       round(net_benefit_qtl, 2),
            "uncertainty":       uncertainty,
            "risk_adj_benefit":  round(risk_adj, 2),
        })

    # Determine overall uncertainty from forecast median band
    avg_rel_width = float(np.mean(
        (forecast_high - forecast_low) / np.where(forecast_median > 0, forecast_median, 1.0)
    ))
    overall_uncertainty = _uncertainty_label(avg_rel_width)

    # Build recommendation
    if best_day == 0:
        action      = "SELL_NOW"
        wait_days   = 0
        exp_price   = latest_price
        exp_gain    = 0.0
        storage_tot = 0.0
        net_ben     = 0.0

        # Explain WHY sell now
        fc_peak = float(np.max(forecast_median))
        fc_min  = float(np.min(forecast_median))

        if fc_peak < latest_price:
            reason = (
                f"Based on available historical data, the 7-day forecast "
                f"(peak ₹{fc_peak:,.0f}/QTL) is below the current market price "
                f"(₹{latest_price:,.0f}/QTL). Selling now is estimated to be better."
            )
        elif (fc_peak - latest_price) < min_benefit_per_qtl:
            reason = (
                f"The forecast does not show a meaningful price increase above "
                f"the current ₹{latest_price:,.0f}/QTL within the 7-day window "
                f"(max forecast: ₹{fc_peak:,.0f}). After storage costs, waiting "
                f"does not provide significant benefit."
            )
        elif overall_uncertainty == "High":
            reason = (
                f"While the forecast suggests a possible rise to ₹{fc_peak:,.0f}/QTL, "
                f"uncertainty is HIGH (wide prediction range). "
                f"Selling now at ₹{latest_price:,.0f}/QTL is the lower-risk option."
            )
        else:
            reason = (
                f"Based on the available forecast, no future day provides "
                f"a risk-adjusted net benefit above ₹{min_benefit_per_qtl}/QTL. "
                f"Consider selling now."
            )
    else:
        action      = f"WAIT_{best_day}_DAYS"
        wait_days   = best_day
        exp_price   = float(forecast_median[best_day - 1])
        exp_gain    = exp_price - latest_price
        storage_tot = storage_cost_per_day * best_day
        net_ben     = exp_gain - storage_tot

        reason = (
            f"Based on available historical data, Day {best_day} shows the best "
            f"risk-adjusted outcome: forecast ₹{exp_price:,.0f}/QTL vs current "
            f"₹{latest_price:,.0f}/QTL. Estimated gain: ₹{exp_gain:,.0f}/QTL. "
            f"Storage cost: ₹{storage_tot:,.0f}/QTL. "
            f"Net benefit: ₹{net_ben:,.0f}/QTL. "
            f"Forecast uncertainty: {overall_uncertainty}."
        )

    # Data quality note
    data_quality_note = None
    if context_n_obs is not None and context_n_obs < 30:
        data_quality_note = (
            f"Only {context_n_obs} historical observations available. "
            "Forecast confidence is reduced — treat this as indicative only."
        )
    elif overall_uncertainty == "High":
        data_quality_note = (
            "High forecast uncertainty detected. "
            "Market volatility is significant — monitor closely before deciding."
        )

    return {
        "action":                action,
        "wait_days":             wait_days,
        "expected_price":        round(exp_price, 2),
        "expected_gain_per_qtl": round(exp_gain, 2),
        "storage_cost_per_qtl":  round(storage_tot, 2),
        "net_benefit_per_qtl":   round(net_ben, 2),
        "uncertainty":           overall_uncertainty,
        "reason":                reason,
        "day_analysis":          day_analysis,
        "data_quality_note":     data_quality_note,
    }
