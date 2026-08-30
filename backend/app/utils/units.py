"""
Unit handling.

Mandi prices are quoted per quintal, farmers often think in kilograms, and
buyers in tonnes. Comparing a per-kg offer against a per-quintal mandi price
without converting would be off by a factor of 100, so every comparison in the
intelligence layer goes through here.
"""
from app.utils.responses import ValidationError

#: How many quintals one unit represents. A BAG is taken as 50 kg, which is
#: the common Maharashtra convention; it is an assumption, not a standard.
QUINTAL_FACTORS = {
    "KG": 0.01,
    "QUINTAL": 1.0,
    "QTL": 1.0,
    "TONNE": 10.0,
    "TON": 10.0,
    "MT": 10.0,
    "BAG": 0.5,
}

#: Counted units cannot be converted to weight without a per-piece weight.
NON_WEIGHT_UNITS = ("DOZEN", "PIECE", "NUMBER", "CRATE")

CANONICAL_UNIT = "QUINTAL"


def normalise_unit(unit):
    return (unit or CANONICAL_UNIT).strip().upper()


def is_convertible(unit):
    return normalise_unit(unit) in QUINTAL_FACTORS


def to_quintals(quantity, unit):
    """Convert a quantity to quintals, or raise if the unit is a count."""
    unit = normalise_unit(unit)
    if unit not in QUINTAL_FACTORS:
        raise ValidationError(
            f"Quantities in '{unit}' cannot be converted to weight. "
            "Use KG, QUINTAL or TONNE for price comparison."
        )
    return float(quantity) * QUINTAL_FACTORS[unit]


def convert_quantity(quantity, from_unit, to_unit):
    """Convert a quantity between two weight units."""
    if quantity is None:
        return None
    from_unit, to_unit = normalise_unit(from_unit), normalise_unit(to_unit)
    if from_unit == to_unit:
        return float(quantity)
    return to_quintals(quantity, from_unit) / QUINTAL_FACTORS[to_unit]


def convert_price(price, from_unit, to_unit):
    """
    Convert a per-unit price between weight units.

    Price moves inversely to quantity: Rs 2,500/quintal is Rs 25/kg.
    """
    if price is None:
        return None
    from_unit, to_unit = normalise_unit(from_unit), normalise_unit(to_unit)
    if from_unit == to_unit:
        return float(price)
    if from_unit not in QUINTAL_FACTORS or to_unit not in QUINTAL_FACTORS:
        raise ValidationError(
            f"Cannot compare a price per {from_unit} with a price per {to_unit}."
        )
    return float(price) * QUINTAL_FACTORS[to_unit] / QUINTAL_FACTORS[from_unit]


def to_tonnes(quantity, unit):
    return to_quintals(quantity, unit) / 10.0


def describe(quantity, unit):
    if quantity is None:
        return "-"
    return f"{float(quantity):,.2f} {normalise_unit(unit).title()}"
