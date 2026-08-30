"""
Short-term price forecasting from historical mandi prices.

Implemented with ordinary least squares and moving averages in plain Python -
no numpy or scikit-learn dependency - because the model is small, the data is
small, and being able to read the arithmetic matters more than speed here.

The single most important behaviour in this module: when there is not enough
history, it says so. It never invents a number.
"""
import datetime as dt
import math

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
LINEAR_TREND = "LINEAR_TREND"
MOVING_AVERAGE = "MOVING_AVERAGE"

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"

RISING = "RISING"
FALLING = "FALLING"
STABLE = "STABLE"

#: A trend smaller than this (percent of price, per week) is called STABLE.
STABLE_BAND_PERCENT_PER_WEEK = 1.5


def _as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value)[:10]
    return dt.datetime.strptime(text, "%Y-%m-%d").date()


def prepare_series(observations):
    """
    Turn raw rows into ``(day_index, price)`` pairs.

    Day index is days since the first observation, so irregular gaps in the
    mandi feed (holidays, no arrivals) do not distort the slope.
    """
    points = []
    for item in observations or []:
        if isinstance(item, dict):
            date_value = item.get("price_date")
            price = item.get("modal_price")
        else:
            date_value, price = item.price_date, item.modal_price
        if date_value is None or price is None:
            continue
        try:
            points.append((_as_date(date_value), float(price)))
        except (ValueError, TypeError):
            continue
    if not points:
        return [], None
    points.sort(key=lambda pair: pair[0])
    # Collapse duplicate dates (several markets on one day) to their average.
    merged = {}
    for date_value, price in points:
        merged.setdefault(date_value, []).append(price)
    ordered = sorted(merged.items())
    start = ordered[0][0]
    series = [((date_value - start).days, sum(prices) / len(prices)) for date_value, prices in ordered]
    return series, start


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def stdev(values):
    values = list(values)
    if len(values) < 2:
        return 0.0
    average = mean(values)
    return math.sqrt(sum((v - average) ** 2 for v in values) / (len(values) - 1))


def moving_average(values, window=7):
    """Trailing moving average. Shorter than one window at the start, on purpose."""
    values = list(values)
    if not values:
        return []
    window = max(1, min(int(window), len(values)))
    return [mean(values[max(0, i - window + 1): i + 1]) for i in range(len(values))]


def linear_regression(series):
    """
    Fit ``price = slope * day + intercept`` by least squares.

    Returns slope, intercept, r-squared and the residual standard deviation.
    """
    n = len(series)
    if n < 2:
        return 0.0, (series[0][1] if series else 0.0), 0.0, 0.0
    xs = [float(x) for x, _ in series]
    ys = [float(y) for _, y in series]
    x_mean, y_mean = mean(xs), mean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return 0.0, y_mean, 0.0, stdev(ys)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    intercept = y_mean - slope * x_mean
    predictions = [slope * x + intercept for x in xs]
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, predictions))
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    residual_sd = math.sqrt(ss_res / (n - 2)) if n > 2 else stdev(ys)
    return slope, intercept, max(0.0, r_squared), residual_sd


def volatility_percent(series):
    """Coefficient of variation, as a percentage. High values mean a noisy market."""
    prices = [price for _, price in series]
    average = mean(prices)
    if average <= 0:
        return 0.0
    return round(100.0 * stdev(prices) / average, 2)


def _confidence(points, r_squared, volatility):
    """
    Grade how much weight the farmer should put on this forecast.

    Deliberately conservative: a good fit on very little data is still LOW,
    because a straight line through eleven points is not knowledge.
    """
    if points >= 25 and r_squared >= 0.55 and volatility < 20:
        return HIGH
    if points >= 15 and (r_squared >= 0.30 or volatility < 12):
        return MEDIUM
    return LOW


def classify_trend(slope, latest_price):
    """Turn a slope in rupees/day into RISING, FALLING or STABLE."""
    if not latest_price:
        return STABLE
    weekly_percent = 100.0 * (slope * 7.0) / float(latest_price)
    if weekly_percent > STABLE_BAND_PERCENT_PER_WEEK:
        return RISING
    if weekly_percent < -STABLE_BAND_PERCENT_PER_WEEK:
        return FALLING
    return STABLE


def forecast_prices(observations, horizon_days=7, min_points=10):
    """
    Forecast the modal price ``horizon_days`` ahead.

    Args:
        observations: rows (or MarketData models) with ``price_date`` and
            ``modal_price``, in any order.
        horizon_days: how far ahead to project.
        min_points: refuse to forecast below this many distinct observations.

    Returns:
        dict: always contains ``available``. When ``available`` is False the
        ``reason`` explains why, and no prices are present. Callers must show
        that message instead of a number.
    """
    series, start_date = prepare_series(observations)
    points = len(series)

    if points < min_points:
        return {
            "available": False,
            "method": INSUFFICIENT_DATA,
            "data_points": points,
            "minimum_required": min_points,
            "confidence": LOW,
            "reason": (
                f"Insufficient historical data for a reliable forecast "
                f"({points} price observations available, {min_points} needed)."
            ),
        }

    prices = [price for _, price in series]
    latest_price = prices[-1]
    slope, intercept, r_squared, residual_sd = linear_regression(series)
    volatility = volatility_percent(series)
    confidence = _confidence(points, r_squared, volatility)
    trend = classify_trend(slope, latest_price)

    # A flat or badly-fitting line is not worth extrapolating; fall back to a
    # moving average, which at least does not pretend to know a direction.
    use_trend = r_squared >= 0.15 and confidence in (MEDIUM, HIGH)
    method = LINEAR_TREND if use_trend else MOVING_AVERAGE
    smoothed = moving_average(prices, window=min(7, points))
    baseline = smoothed[-1]

    last_day = series[-1][0]
    projections = []
    for day_offset in range(1, int(horizon_days) + 1):
        day_index = last_day + day_offset
        if method == LINEAR_TREND:
            value = slope * day_index + intercept
        else:
            value = baseline
        # Widen the band the further out we look - uncertainty grows with time.
        margin = 1.96 * residual_sd * math.sqrt(1.0 + day_offset / max(points, 1))
        projections.append(
            {
                "day_offset": day_offset,
                "forecast_date": (start_date + dt.timedelta(days=day_index)).isoformat(),
                "forecast_price": round(max(0.0, value), 2),
                "lower_bound": round(max(0.0, value - margin), 2),
                "upper_bound": round(value + margin, 2),
            }
        )

    final = projections[-1]
    change_amount = final["forecast_price"] - latest_price
    change_percent = (100.0 * change_amount / latest_price) if latest_price else 0.0

    return {
        "available": True,
        "method": method,
        # A moving-average fallback means we explicitly did NOT trust the slope
        # enough to extrapolate it. The observed direction is still reported,
        # but callers must not act on it as if it were a forecast.
        "trend_is_reliable": method == LINEAR_TREND,
        "data_points": points,
        "history_days": series[-1][0] - series[0][0] + 1,
        "latest_price": round(latest_price, 2),
        "horizon_days": int(horizon_days),
        "forecast_price": final["forecast_price"],
        "lower_bound": final["lower_bound"],
        "upper_bound": final["upper_bound"],
        "expected_change": round(change_amount, 2),
        "expected_change_percent": round(change_percent, 2),
        "trend": trend,
        "slope_per_day": round(slope, 4),
        "r_squared": round(r_squared, 3),
        "volatility_percent": volatility,
        "confidence": confidence,
        "projections": projections,
        "moving_average_7d": round(baseline, 2),
        "notes": (
            "Projected from historical modal prices using "
            + ("a least-squares trend line." if method == LINEAR_TREND else
               "a 7-day moving average, because the trend fit was too weak to extrapolate.")
        ),
    }


def summarise_arrivals(observations):
    """
    Describe how arrivals are moving, without claiming it causes a price move.

    High arrivals often coincide with softer prices, but stating that as a rule
    would be a causal claim this project has no evidence for.
    """
    values = []
    for item in observations or []:
        raw = item.get("arrival_quantity") if isinstance(item, dict) else item.arrival_quantity
        if raw is not None:
            values.append(float(raw))
    if len(values) < 3:
        return {
            "available": False,
            "reason": "Arrival volume is not published for this market and crop.",
        }
    recent = values[-3:]
    earlier = values[:-3] or values
    recent_avg, earlier_avg = mean(recent), mean(earlier)
    change_percent = (100.0 * (recent_avg - earlier_avg) / earlier_avg) if earlier_avg else 0.0
    if change_percent > 15:
        direction = "RISING"
    elif change_percent < -15:
        direction = "FALLING"
    else:
        direction = "STABLE"
    return {
        "available": True,
        "latest": round(values[-1], 2),
        "recent_average": round(recent_avg, 2),
        "previous_average": round(earlier_avg, 2),
        "change_percent": round(change_percent, 2),
        "direction": direction,
        "observations": len(values),
        "note": "Arrival volumes are shown as market context only.",
    }
