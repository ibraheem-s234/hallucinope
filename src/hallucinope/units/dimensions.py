"""Physical dimensions as exponent vectors over base quantities.

A dimension says what *kind* of quantity something is, independent of the
unit it is written in. Speed is length^1 * time^-1 whether it is written in
km/h or mph. Two units can be converted only if their dimensions are equal.
"""

from __future__ import annotations

from dataclasses import dataclass

# Order matters: each Dimension stores one exponent per base, in this order.
BASES = ("length", "mass", "time", "temperature")

_SUPERSCRIPTS = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


@dataclass(frozen=True)
class Dimension:
    """Exponents of each base quantity, e.g. speed = (1, 0, -1, 0)."""

    exponents: tuple[int, ...] = (0,) * len(BASES)

    def __post_init__(self) -> None:
        if len(self.exponents) != len(BASES):
            raise ValueError(f"expected {len(BASES)} exponents, got {len(self.exponents)}")

    def __mul__(self, other: Dimension) -> Dimension:
        return Dimension(tuple(a + b for a, b in zip(self.exponents, other.exponents)))

    def __truediv__(self, other: Dimension) -> Dimension:
        return Dimension(tuple(a - b for a, b in zip(self.exponents, other.exponents)))

    def __pow__(self, power: int) -> Dimension:
        return Dimension(tuple(a * power for a in self.exponents))

    @property
    def name(self) -> str | None:
        """Human-friendly name such as 'speed', or None if it has no common name."""
        return NAMED.get(self)

    def __str__(self) -> str:
        parts = []
        for base, exp in zip(BASES, self.exponents):
            if exp == 1:
                parts.append(base)
            elif exp != 0:
                parts.append(base + str(exp).translate(_SUPERSCRIPTS))
        formula = "·".join(parts) or "dimensionless"
        if self.name is None or self.name == formula:
            return formula
        return f"{self.name} ({formula})"


def _base(index: int) -> Dimension:
    exps = [0] * len(BASES)
    exps[index] = 1
    return Dimension(tuple(exps))


DIMENSIONLESS = Dimension()
LENGTH = _base(0)
MASS = _base(1)
TIME = _base(2)
TEMPERATURE = _base(3)

AREA = LENGTH**2
VOLUME = LENGTH**3
SPEED = LENGTH / TIME

NAMED: dict[Dimension, str] = {
    LENGTH: "length",
    MASS: "mass",
    TIME: "time",
    TEMPERATURE: "temperature",
    AREA: "area",
    VOLUME: "volume",
    SPEED: "speed",
}
