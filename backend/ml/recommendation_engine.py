"""
The hero feature: turn a lot plus a set of selling opportunities into one
ranked, explained recommendation.

Two rules shape everything here.

1. Rank on NET realization, never on the headline price. The highest gross
   price is regularly not the best deal once transport and mandi charges are
   taken out, and telling a farmer otherwise is the exact information problem
   this project exists to fix.
2. Every number shown must be traceable to an input. If a cost is an estimate
   it is labelled an estimate; if a comparison could not be made, the reason is
   given instead of a fabricated value.
"""
from ml.matching_model import rank_matches, score_match

SELL_NOW = "SELL_NOW"
CONSIDER_WAITING = "CONSIDER_WAITING"
MONITOR = "MONITOR"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"


def net_realization(gross_amount, costs):
    """
    Break a gross sale value down into what the seller actually keeps.

    Args:
        gross_amount: price x quantity, before any deduction.
        costs: mapping of cost name to amount (transport, commission, storage,
            other). Missing entries count as zero.

    Returns:
        dict: the gross, each deduction, the total deducted and the net.
    """
    gross_amount = float(gross_amount or 0)
    breakdown = {
        "transport": round(float(costs.get("transport") or 0), 2),
        "commission": round(float(costs.get("commission") or 0), 2),
        "storage": round(float(costs.get("storage") or 0), 2),
        "other": round(float(costs.get("other") or 0), 2),
    }
    total_costs = round(sum(breakdown.values()), 2)
    return {
        "gross_amount": round(gross_amount, 2),
        "deductions": breakdown,
        "total_deductions": total_costs,
        "net_amount": round(gross_amount - total_costs, 2),
        "deduction_percent": round(100.0 * total_costs / gross_amount, 2) if gross_amount else 0.0,
    }


#: How much of the distance weight survives once transport cost has already
#: been deducted from the price. See :func:`net_adjusted_weights`.
DISTANCE_WEIGHT_RETAINED = 0.5


def net_adjusted_weights(weights):
    """
    Rebalance the matching weights for ranking on NET realization.

    The configured weights assume the price component holds a *quoted* price.
    Here the price component holds the net price, which already has transport
    deducted - so scoring distance at full weight would charge the farmer for
    the same journey twice, and would systematically push them towards the
    nearest buyer even when a further one pays materially more after costs.

    Half the distance weight is kept, standing for the real frictions money
    does not capture: travel time, spoilage in transit, and the difficulty of
    resolving a problem with a buyer 200 km away. The other half moves to
    price, where the money actually is.
    """
    adjusted = dict(weights)
    distance_weight = float(adjusted.get("distance", 0.0))
    retained = distance_weight * DISTANCE_WEIGHT_RETAINED
    adjusted["distance"] = round(retained, 4)
    adjusted["price"] = round(float(adjusted.get("price", 0.0)) + (distance_weight - retained), 4)
    return adjusted


def evaluate_option(lot, option, weights, benchmark_price, max_distance_km):
    """
    Cost out one selling opportunity and score it.

    The scoring engine is fed the NET price per unit, not the quoted price, so
    a buyer who quotes high but sits 200 km away cannot outrank a nearer buyer
    on the price component alone.
    """
    quantity = float(option.get("tradeable_quantity") or lot.get("quantity") or 0)
    price = option.get("price_per_unit")
    gross = float(price or 0) * quantity
    realization = net_realization(gross, option.get("costs") or {})
    net_per_unit = round(realization["net_amount"] / quantity, 2) if quantity else None

    candidate = dict(option.get("match_inputs") or {})
    candidate["price"] = net_per_unit
    scored = score_match(
        lot,
        candidate,
        weights,
        max_distance_km=max_distance_km,
        benchmark_price=benchmark_price,
    )

    result = dict(option)
    result.update(
        {
            "quantity": round(quantity, 2),
            "gross_price_per_unit": round(float(price), 2) if price is not None else None,
            "net_price_per_unit": net_per_unit,
            "realization": realization,
            "match_score": scored["total_score"],
            "score_components": scored["components"],
            "blockers": scored["blockers"],
            "is_viable": scored["is_viable"],
        }
    )
    result.pop("match_inputs", None)
    return result


def evaluate_options(lot, options, weights, benchmark_price=None, max_distance_km=300.0):
    """
    Cost out and score every opportunity, best first.

    Weights are rebalanced by :func:`net_adjusted_weights` first, because these
    options are ranked on net realization rather than on quoted price.
    """
    adjusted = net_adjusted_weights(weights)
    evaluated = [
        evaluate_option(lot, option, adjusted, benchmark_price, max_distance_km)
        for option in options
    ]
    return rank_matches(evaluated, key="match_score")


def compare_top_options(ranked):
    """
    The comparison table that makes price discovery real.

    A single recommended buyer is not price discovery. Showing what each
    channel would actually pay, side by side, is.
    """
    rows = []
    for option in ranked:
        rows.append(
            {
                "rank": option.get("rank"),
                "option_type": option.get("option_type"),
                "option_id": option.get("option_id"),
                "label": option.get("label"),
                "channel": option.get("channel"),
                "gross_price_per_unit": option.get("gross_price_per_unit"),
                "net_price_per_unit": option.get("net_price_per_unit"),
                "estimated_net_total": option.get("realization", {}).get("net_amount"),
                "total_deductions": option.get("realization", {}).get("total_deductions"),
                "distance_km": option.get("score_components", {})
                .get("distance", {})
                .get("distance_km"),
                "match_score": option.get("match_score"),
                "is_viable": option.get("is_viable"),
            }
        )
    return rows


def explain_recommendation(best, runner_up=None, unit="QUINTAL"):
    """
    Build the "WHY THIS RECOMMENDATION?" list.

    Each line restates a number the farmer can already see above it, so the
    explanation is a summary of the arithmetic, not a separate claim.
    """
    if not best:
        return []

    components = best.get("score_components", {})
    reasons = []

    price = components.get("price", {})
    if price.get("available"):
        reasons.append(price["reason"])
    else:
        reasons.append(
            f"Estimated net realization of Rs {best.get('net_price_per_unit')}/{unit.lower()} "
            "after costs."
        )

    quality = components.get("quality", {})
    if quality.get("available"):
        reasons.append(quality["reason"])

    quantity = components.get("quantity", {})
    if quantity.get("available"):
        reasons.append(quantity["reason"])

    distance = components.get("distance", {})
    reasons.append(distance.get("reason", ""))

    trust = components.get("trust", {})
    if trust.get("reason"):
        reasons.append(trust["reason"])

    realization = best.get("realization", {})
    deductions = realization.get("total_deductions", 0)
    if deductions:
        parts = [
            f"{name} Rs {amount:,.0f}"
            for name, amount in (realization.get("deductions") or {}).items()
            if amount
        ]
        reasons.append(
            f"Estimated costs of Rs {deductions:,.0f} ({', '.join(parts)}) have already been "
            f"subtracted, leaving Rs {realization.get('net_amount', 0):,.0f}."
        )

    if runner_up and runner_up.get("net_price_per_unit") is not None:
        reasons.extend(_compare_with_runner_up(best, runner_up, unit))

    return [reason for reason in reasons if reason]


#: Component names as a farmer would read them.
COMPONENT_LABELS = {
    "price": "a better net price",
    "quantity": "a closer quantity fit",
    "quality": "a better quality match",
    "distance": "a shorter distance",
    "trust": "a stronger buyer reliability record",
}


def _compare_with_runner_up(best, runner_up, unit):
    """
    Say plainly how the winner compares with the next option.

    The case that matters most is when the recommended option nets LESS than
    the runner-up. That happens when distance, quality fit or buyer reliability
    outweigh a small price gap, and the farmer is owed that reasoning rather
    than being left to spot the contradiction themselves.
    """
    gap = (best.get("net_price_per_unit") or 0) - runner_up["net_price_per_unit"]
    unit_label = unit.lower()

    if gap >= 0.01:
        return [
            f"Nets Rs {gap:,.2f}/{unit_label} more than the next option "
            f"({runner_up.get('label')})."
        ]

    best_components = best.get("score_components", {})
    other_components = runner_up.get("score_components", {})
    advantages = [
        COMPONENT_LABELS[name]
        for name in ("quality", "trust", "distance", "quantity")
        if best_components.get(name, {}).get("score", 0)
        - other_components.get(name, {}).get("score", 0)
        > 0.05
    ]

    if gap <= -0.01 and advantages:
        return [
            f"{runner_up.get('label')} quotes a higher net price "
            f"(by Rs {abs(gap):,.2f}/{unit_label}), but this option was ranked first for "
            f"{' and '.join(advantages)}. Both are shown so the choice stays with the farmer."
        ]
    if gap <= -0.01:
        return [
            f"{runner_up.get('label')} nets Rs {abs(gap):,.2f}/{unit_label} more and is worth "
            "comparing before deciding."
        ]
    return [
        f"Nets about the same as {runner_up.get('label')}; the deciding factors were "
        "quality fit, distance and buyer reliability."
    ]


def sale_window_advice(
    forecast,
    best_net_price_per_unit,
    holding_cost_per_unit,
    horizon_days,
    has_active_demand=True,
    is_perishable=False,
    shelf_life_days=None,
    storage_available=True,
    gain_margin_percent=2.0,
):
    """
    Answer the second half of the question: sell now, or wait?

    Waiting is only advised when the forecast gain clearly beats the cost of
    holding the crop, and only when the forecast itself is trustworthy. Every
    other case resolves to selling now or to monitoring, never to a confident
    "wait" the data does not support.
    """
    reasons = []
    best_net_price_per_unit = float(best_net_price_per_unit or 0)
    holding_cost_per_unit = float(holding_cost_per_unit or 0)

    # A crop that will spoil inside the waiting window is not a timing decision.
    if is_perishable and shelf_life_days is not None and shelf_life_days <= horizon_days:
        return {
            "recommendation": SELL_NOW,
            "confidence": HIGH,
            "reasons": [
                f"This crop keeps for about {int(shelf_life_days)} days, which is less than "
                f"the {int(horizon_days)}-day waiting window being considered.",
                "Holding it risks quality loss that would outweigh any price gain.",
            ],
            "expected_gain_per_unit": None,
            "holding_cost_per_unit": round(holding_cost_per_unit, 2),
        }

    if not forecast or not forecast.get("available"):
        return {
            "recommendation": INSUFFICIENT_DATA,
            "confidence": LOW,
            "reasons": [
                forecast.get("reason")
                if forecast
                else "No price history is available for this crop and market.",
                "Insufficient data for a reliable timing recommendation. "
                "Compare the current options on net realization instead.",
            ],
            "expected_gain_per_unit": None,
            "holding_cost_per_unit": round(holding_cost_per_unit, 2),
        }

    trend = forecast.get("trend")
    confidence = forecast.get("confidence", LOW)
    # When the model fell back to a moving average it is saying the trend was
    # not solid enough to extrapolate. Treating that direction as a forecast
    # would be exactly the fabrication this project must not do.
    trend_is_reliable = forecast.get("trend_is_reliable", True)
    change_percent = float(forecast.get("expected_change_percent") or 0)
    expected_gain = best_net_price_per_unit * change_percent / 100.0
    net_benefit = expected_gain - holding_cost_per_unit
    required_margin = best_net_price_per_unit * float(gain_margin_percent) / 100.0

    if trend_is_reliable:
        reasons.append(
            f"Price trend over the last {forecast.get('history_days', 0)} days is "
            f"{trend.lower()}; the {int(horizon_days)}-day projection is "
            f"{change_percent:+.1f}% (forecast confidence: {confidence.lower()})."
        )
    else:
        reasons.append(
            f"Prices over the last {forecast.get('history_days', 0)} days have moved "
            f"{trend.lower()}, but the trend is not steady enough to project forward, "
            "so no price gain is being assumed."
        )
    if holding_cost_per_unit > 0:
        reasons.append(
            f"Holding the crop for {int(horizon_days)} days is estimated to cost "
            f"Rs {holding_cost_per_unit:,.2f} per unit in storage and expected loss."
        )
    elif not storage_available:
        reasons.append(
            "No storage facility was found nearby, so waiting would mean keeping the crop "
            "on farm at the farmer's own risk."
        )

    if confidence == LOW:
        recommendation = MONITOR
        reasons.append(
            "The forecast is not confident enough to justify holding stock. "
            "Watch prices for a few more days before deciding."
        )
        window_confidence = LOW
    elif not trend_is_reliable:
        # No dependable direction: holding is a gamble, but so is claiming the
        # price will fall. Say what we can defend and no more.
        recommendation = SELL_NOW if holding_cost_per_unit > 0 else MONITOR
        reasons.append(
            "Without a dependable price trend there is no evidence that waiting "
            "would beat the cost of holding the crop."
            if holding_cost_per_unit > 0
            else "Without a dependable price trend, keep watching prices rather than "
            "committing either way."
        )
        window_confidence = LOW
    elif trend == "FALLING":
        recommendation = SELL_NOW
        reasons.append("Prices are trending down, so waiting is likely to reduce realization.")
        window_confidence = confidence
    elif net_benefit > required_margin and storage_available:
        recommendation = CONSIDER_WAITING
        reasons.append(
            f"After holding costs, waiting is projected to add about "
            f"Rs {net_benefit:,.2f} per unit - enough to be worth considering."
        )
        window_confidence = MEDIUM if confidence == HIGH else LOW
    elif net_benefit > 0:
        recommendation = MONITOR
        reasons.append(
            f"The projected gain after holding costs (Rs {net_benefit:,.2f} per unit) is too "
            "small to be relied on. Keep watching rather than committing to hold."
        )
        window_confidence = LOW
    else:
        recommendation = SELL_NOW
        reasons.append(
            "The projected price gain does not cover the cost of holding the crop."
        )
        window_confidence = confidence

    if recommendation != SELL_NOW and not has_active_demand:
        # Waiting is far riskier when nobody is currently buying.
        recommendation = MONITOR if recommendation == CONSIDER_WAITING else recommendation
        reasons.append(
            "There is no active buyer demand for this crop right now, "
            "which makes holding stock riskier."
        )
    if recommendation == SELL_NOW and has_active_demand:
        reasons.append("Suitable buyer demand is active now.")

    return {
        "recommendation": recommendation,
        "confidence": window_confidence,
        "expected_gain_per_unit": round(expected_gain, 2),
        "holding_cost_per_unit": round(holding_cost_per_unit, 2),
        "net_benefit_per_unit": round(net_benefit, 2),
        "horizon_days": int(horizon_days),
        "forecast_trend": trend,
        "forecast_confidence": confidence,
        "reasons": reasons,
    }
