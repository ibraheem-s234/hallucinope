"""Tests for the units engine: parsing, conversion, and claim checking."""

import pytest

from hallucinope.units.convert import IncompatibleUnitsError, check_conversion, convert
from hallucinope.units.dimensions import AREA, LENGTH, SPEED, TIME, VOLUME
from hallucinope.units.registry import OffsetUnitError, UnknownUnitError, parse_unit

# --- Exact conversions against official definitions -------------------------

EXACT = [
    (1, "mi", "km", 1.609344),
    (1, "ft", "m", 0.3048),
    (1, "lb", "kg", 0.45359237),
    (100, "km/h", "m/s", 27.7777777778),
    (60, "mph", "km/h", 96.56064),
    (1, "acre", "m²", 4046.8564224),
    (1, "gallon", "L", 3.785411784),
    (1, "sq ft", "m^2", 0.09290304),
    (1, "yr", "day", 365.25),
    (1, "knot", "km/h", 1.852),
]


@pytest.mark.parametrize("value, src, dst, expected", EXACT)
def test_exact_conversions(value, src, dst, expected):
    assert convert(value, src, dst) == pytest.approx(expected, rel=1e-9)


# --- Temperature: offsets, not just scale factors --------------------------

@pytest.mark.parametrize("value, src, dst, expected", [
    (0, "°C", "°F", 32.0),
    (100, "°C", "°F", 212.0),
    (-40, "°C", "°F", -40.0),
    (98.6, "°F", "°C", 37.0),
    (0, "K", "°C", -273.15),
    (100, "celsius", "kelvin", 373.15),
])
def test_temperature_conversions(value, src, dst, expected):
    assert convert(value, src, dst) == pytest.approx(expected, abs=1e-9)


def test_float_noise_is_removed():
    assert convert(0, "°C", "°F") == 32.0  # exact, not 31.999999999999986


# --- Parsing: how people actually write units ------------------------------

@pytest.mark.parametrize("text, dimension", [
    ("kilometres", LENGTH),
    ("miles", LENGTH),
    ("inches", LENGTH),
    ("hrs", TIME),
    ("square feet", AREA),
    ("m²", AREA),
    ("cubic metres", VOLUME),
    ("ft³", VOLUME),
    ("fl oz", VOLUME),
    ("miles per hour", SPEED),
    ("km/h", SPEED),
])
def test_parses_to_correct_dimension(text, dimension):
    assert parse_unit(text).dimension == dimension


def test_compound_and_named_units_agree():
    assert convert(1, "miles per hour", "mph") == pytest.approx(1.0)
    assert convert(1, "km/h", "kph") == pytest.approx(1.0)


def test_parser_keeps_users_spelling():
    assert parse_unit("kilometres").symbol == "kilometres"


def test_round_trip_returns_original():
    for src, dst in [("km", "mi"), ("°F", "°C"), ("acre", "ha"), ("lb", "oz")]:
        assert convert(convert(123.45, src, dst), dst, src) == pytest.approx(123.45)


# --- Errors: refuse rather than guess ---------------------------------------

@pytest.mark.parametrize("text", ["bananas", "m2", "ms", "", "   "])
def test_unknown_units_raise(text):
    with pytest.raises(UnknownUnitError):
        parse_unit(text)


@pytest.mark.parametrize("src, dst", [("kg", "m"), ("km/h", "km"), ("°C", "kg")])
def test_incompatible_units_raise(src, dst):
    with pytest.raises(IncompatibleUnitsError):
        convert(1, src, dst)


@pytest.mark.parametrize("text", ["°C/s", "°F²", "celsius per hour"])
def test_offset_units_cannot_be_compounded(text):
    with pytest.raises(OffsetUnitError):
        parse_unit(text)


# --- Claim checking: what the fact-checker uses ----------------------------

def test_wrong_conversion_is_flagged_with_true_value():
    result = check_conversion(100, "km", 50, "mi")
    assert not result.correct
    assert result.expected == pytest.approx(62.137, rel=1e-4)
    assert "62.14" in result.message


@pytest.mark.parametrize("stated", [62.14, 62, 60])
def test_rounded_conversions_pass(stated):
    assert check_conversion(100, "km", stated, "mi").correct


def test_temperature_claims_use_absolute_tolerance():
    assert check_conversion(20, "°C", 68, "°F").correct
    assert check_conversion(20, "°C", 69, "°F").correct      # 0.56 °C off
    assert not check_conversion(20, "°C", 72, "°F").correct  # 2.2 °C off


def test_claim_comparing_different_quantities_raises():
    with pytest.raises(IncompatibleUnitsError):
        check_conversion(5, "kg", 5, "m")


# --- v1.1: kitchen units --------------------------------------------------------

@pytest.mark.parametrize("value, src, dst, expected", [
    (1, "US cup", "mL", 236.5882365),
    (2, "cups", "mL", 473.176473),
    (1, "metric cup", "mL", 250),
    (1, "tablespoon", "mL", 14.78676478125),
    (3, "teaspoons", "tablespoon", 1),
])
def test_kitchen_units(value, src, dst, expected):
    assert convert(value, src, dst) == pytest.approx(expected, rel=1e-9)
