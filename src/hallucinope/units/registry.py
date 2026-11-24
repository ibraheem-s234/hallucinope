"""The unit table, and parsing of unit strings such as 'km/h' or 'square feet'.

Every unit is stored as an affine map to SI:  si_value = value * scale + offset.
Only temperature units have a non-zero offset, and those units may not be
combined into compound units (°C/s, °F² ...), because offsets do not survive
multiplication. That restriction is enforced here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dimensions import AREA, LENGTH, MASS, SPEED, TEMPERATURE, TIME, VOLUME, Dimension


class UnknownUnitError(ValueError):
    """The unit string does not name any unit Hallucinope knows."""


class OffsetUnitError(ValueError):
    """An offset unit (°C, °F) was used inside a compound unit."""


@dataclass(frozen=True)
class Unit:
    symbol: str
    dimension: Dimension
    scale: float
    offset: float = 0.0

    def _require_no_offset(self) -> None:
        if self.offset:
            raise OffsetUnitError(
                f"'{self.symbol}' has an offset from absolute zero and cannot be "
                "part of a compound unit; use K for temperature differences"
            )

    def __mul__(self, other: Unit) -> Unit:
        self._require_no_offset()
        other._require_no_offset()
        return Unit(f"{self.symbol}·{other.symbol}", self.dimension * other.dimension,
                    self.scale * other.scale)

    def __truediv__(self, other: Unit) -> Unit:
        self._require_no_offset()
        other._require_no_offset()
        return Unit(f"{self.symbol}/{other.symbol}", self.dimension / other.dimension,
                    self.scale / other.scale)

    def __pow__(self, power: int) -> Unit:
        if power == 1:
            return self
        self._require_no_offset()
        return Unit(f"{self.symbol}^{power}", self.dimension**power, self.scale**power)


def _define(table: dict[str, Unit], aliases: str, dimension: Dimension,
            scale: float, offset: float = 0.0) -> None:
    names = aliases.split("|")
    unit = Unit(names[0], dimension, scale, offset)
    for name in names:
        table[name.lower()] = unit


# Keys are lowercase; lookups lowercase their input. Scale factors are exact
# international definitions unless noted.
UNITS: dict[str, Unit] = {}
_d = _define
# Length (SI: metre)
_d(UNITS, "m|metre|meter", LENGTH, 1.0)
_d(UNITS, "km|kilometre|kilometer|klick", LENGTH, 1000.0)
_d(UNITS, "cm|centimetre|centimeter", LENGTH, 0.01)
_d(UNITS, "mm|millimetre|millimeter", LENGTH, 0.001)
_d(UNITS, "mi|mile", LENGTH, 1609.344)
_d(UNITS, "yd|yard", LENGTH, 0.9144)
_d(UNITS, "ft|foot|feet", LENGTH, 0.3048)
_d(UNITS, "in|inch|inches", LENGTH, 0.0254)
_d(UNITS, "nmi|nautical mile", LENGTH, 1852.0)
# Mass (SI: kilogram)
_d(UNITS, "kg|kgs|kilogram|kilo", MASS, 1.0)
_d(UNITS, "g|gram|gramme", MASS, 0.001)
_d(UNITS, "mg|milligram", MASS, 1e-6)
_d(UNITS, "t|tonne|metric ton", MASS, 1000.0)
_d(UNITS, "lb|lbs|pound", MASS, 0.45359237)
_d(UNITS, "oz|ounce", MASS, 0.028349523125)
_d(UNITS, "st|stone", MASS, 6.35029318)
# Time (SI: second). A year is the Julian year, 365.25 days.
_d(UNITS, "s|sec|second", TIME, 1.0)
_d(UNITS, "min|minute", TIME, 60.0)
_d(UNITS, "h|hr|hrs|hour", TIME, 3600.0)
_d(UNITS, "day|d", TIME, 86400.0)
_d(UNITS, "week|wk", TIME, 604800.0)
_d(UNITS, "yr|yrs|year", TIME, 31557600.0)
# Temperature (SI: kelvin). °F: K = (F + 459.67) * 5/9
_d(UNITS, "K|kelvin", TEMPERATURE, 1.0)
_d(UNITS, "°C|degC|celsius|degree celsius|degrees celsius", TEMPERATURE, 1.0, 273.15)
_d(UNITS, "°F|degF|fahrenheit|degree fahrenheit|degrees fahrenheit",
   TEMPERATURE, 5 / 9, 459.67 * 5 / 9)
# Named area and volume units (compound ones like km² come from parsing)
_d(UNITS, "ha|hectare", AREA, 10_000.0)
_d(UNITS, "acre", AREA, 4046.8564224)
_d(UNITS, "L|l|litre|liter", VOLUME, 0.001)
_d(UNITS, "mL|ml|millilitre|milliliter", VOLUME, 1e-6)
_d(UNITS, "gal|gallon|us gallon", VOLUME, 0.003785411784)
_d(UNITS, "fl oz|fluid ounce|us fl oz|us fluid ounce", VOLUME, 2.95735295625e-5)
# Kitchen units (US customary; "cup" means a US cup unless "metric cup" is said)
_d(UNITS, "cup|us cup", VOLUME, 2.365882365e-4)
_d(UNITS, "metric cup", VOLUME, 2.5e-4)
_d(UNITS, "tbsp|tablespoon|us tablespoon", VOLUME, 1.478676478125e-5)
_d(UNITS, "tsp|teaspoon|us teaspoon", VOLUME, 4.92892159375e-6)
# Named speed units
_d(UNITS, "mph", SPEED, 0.44704)
_d(UNITS, "kph|kmh|km/h", SPEED, 1000 / 3600)
_d(UNITS, "kn|knot", SPEED, 1852 / 3600)
del _d

_SUPERSCRIPT_POWERS = {"²": 2, "³": 3}
_POWER_WORDS = {"square": 2, "sq": 2, "cubic": 3, "cu": 3}


def lookup(name: str) -> Unit:
    """Find a single (non-compound) unit by symbol or name, plurals allowed."""
    key = " ".join(name.strip().lower().split())
    if key in UNITS:
        return UNITS[key]
    # Plurals (miles, hours) only for names of 3+ letters, so a short symbol
    # like 'ms' is never silently read as 'm'.
    if key.endswith("s") and len(key) > 3 and key[:-1] in UNITS:
        return UNITS[key[:-1]]
    raise UnknownUnitError(f"unknown unit: '{name.strip()}'")


def _parse_factor(text: str) -> Unit:
    """One factor of a compound unit: 'km', 'm^2', 'ft³', 'square feet'."""
    text = " ".join(text.split())
    words = text.lower().split(" ", 1)
    if len(words) == 2 and words[0] in _POWER_WORDS:
        return lookup(words[1]) ** _POWER_WORDS[words[0]]
    match = re.fullmatch(r"(.+?)\s*\^\s*(-?\d+)", text)
    if match:
        return lookup(match.group(1)) ** int(match.group(2))
    if text and text[-1] in _SUPERSCRIPT_POWERS:
        return lookup(text[:-1]) ** _SUPERSCRIPT_POWERS[text[-1]]
    return lookup(text)


def parse_unit(text: str) -> Unit:
    """Parse a unit string, compound or not: 'km/h', 'miles per hour', 'm²'."""
    if not text or not text.strip():
        raise UnknownUnitError("empty unit")
    try:  # whole-string match first, so names like 'km/h' or 'fl oz' win
        unit = lookup(text)
    except UnknownUnitError:
        normalized = re.sub(r"\s+per\s+", "/", text.strip(), flags=re.IGNORECASE)
        numerator, *denominators = normalized.split("/")
        unit = _parse_factor(numerator)
        for den in denominators:
            unit = unit / _parse_factor(den)
    # Keep the user's own spelling, so messages echo what they wrote.
    return Unit(text.strip(), unit.dimension, unit.scale, unit.offset)
