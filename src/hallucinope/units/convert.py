"""Unit conversion, and checking whether a stated conversion is correct.

convert() turns a value from one unit into another, refusing if the units
measure different kinds of quantity. check_conversion() is what the
fact-checker uses: given a claim like "100 km (about 50 miles)", it computes
the true value and says whether the stated one is within tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dimensions import TEMPERATURE
from .registry import Unit, parse_unit


class IncompatibleUnitsError(ValueError):
    """The two units measure different kinds of quantity (e.g. kg and m)."""


def _resolve(unit: str | Unit) -> Unit:
    return unit if isinstance(unit, Unit) else parse_unit(unit)


def convert(value: float, from_unit: str | Unit, to_unit: str | Unit) -> float:
    """Convert value from one unit to another, e.g. convert(100, 'km/h', 'm/s')."""
    src, dst = _resolve(from_unit), _resolve(to_unit)
    if src.dimension != dst.dimension:
        raise IncompatibleUnitsError(
            f"cannot convert {src.symbol} ({src.dimension}) "
            f"to {dst.symbol} ({dst.dimension})"
        )
    si_value = value * src.scale + src.offset
    result = (si_value - dst.offset) / dst.scale
    # Round to 12 significant digits to strip float noise (0 °C -> 32 °F,
    # not 31.999999999999986). Far finer than any real-world claim.
    return float(f"{result:.12g}")


def _fmt(x: float) -> str:
    """Readable number: 62.14, 0.2778, 1,609,344."""
    return f"{round(x):,}" if abs(x) >= 1000 else f"{x:.4g}"


@dataclass(frozen=True)
class ConversionCheck:
    correct: bool
    expected: float      # the true value, in the stated unit
    stated: float
    message: str


# Defaults: claims in prose are usually rounded ("about 60 miles"), so a
# small relative error is accepted. Temperatures use an absolute tolerance
# instead, because relative error is meaningless near 0 °C or 0 °F.
DEFAULT_REL_TOL = 0.05
DEFAULT_TEMP_TOL_K = 1.0


def check_conversion(
    value: float,
    unit: str | Unit,
    stated_value: float,
    stated_unit: str | Unit,
    rel_tol: float = DEFAULT_REL_TOL,
    temp_tol_k: float = DEFAULT_TEMP_TOL_K,
) -> ConversionCheck:
    """Check a claim of the form '<value> <unit> is <stated_value> <stated_unit>'.

    Raises IncompatibleUnitsError if the claim compares different quantities.
    """
    src, dst = _resolve(unit), _resolve(stated_unit)
    expected = convert(value, src, dst)

    if dst.dimension == TEMPERATURE:
        # Compare in kelvin-sized steps so the tolerance means the same thing
        # whether the claim is in °C, °F or K.
        error_k = abs(stated_value - expected) * dst.scale
        correct = error_k <= temp_tol_k
        detail = f"off by {_fmt(abs(stated_value - expected))} {dst.symbol}"
    else:
        rel_error = abs(stated_value - expected) / abs(expected) if expected else (
            0.0 if stated_value == 0 else float("inf"))
        correct = rel_error <= rel_tol
        detail = f"off by {rel_error:.1%}"

    claim = f"{_fmt(value)} {src.symbol} = {_fmt(expected)} {dst.symbol}"
    if correct:
        message = f"correct: {claim}"
    else:
        message = f"wrong: {claim}, not {_fmt(stated_value)} {dst.symbol} ({detail})"
    return ConversionCheck(correct, expected, stated_value, message)
