"""Unit conversion - the quiet source of hundredfold pricing errors."""
import pytest

from app.utils.responses import ValidationError
from app.utils.units import convert_price, convert_quantity, to_quintals, to_tonnes


def test_weight_conversions_round_trip():
    assert to_quintals(1000, "KG") == 10
    assert to_quintals(1, "TONNE") == 10
    assert to_tonnes(100, "QUINTAL") == 10
    assert convert_quantity(500, "KG", "QUINTAL") == 5


def test_price_moves_inversely_to_quantity():
    """Rs 2,500 per quintal is Rs 25 per kilogram, not Rs 250,000."""
    assert convert_price(2500, "QUINTAL", "KG") == pytest.approx(25)
    assert convert_price(25, "KG", "QUINTAL") == pytest.approx(2500)
    assert convert_price(2500, "QUINTAL", "TONNE") == pytest.approx(25000)


def test_identical_units_pass_through_untouched():
    assert convert_price(2500, "QUINTAL", "QUINTAL") == 2500
    assert convert_quantity(7, "KG", "KG") == 7


def test_counted_units_refuse_to_become_weights():
    """A dozen bananas has no defensible weight, so we refuse rather than guess."""
    with pytest.raises(ValidationError):
        to_quintals(10, "DOZEN")
    with pytest.raises(ValidationError):
        convert_price(100, "DOZEN", "QUINTAL")
