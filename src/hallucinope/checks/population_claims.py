"""Judging population claims: correct, wrong, unconfirmed, or can't verify.

Three rules (approved 2026-11-18):

1. Respect how the number was written. "41.7 million" claims precision to
   the nearest 100,000; "40 million" only to the nearest 10 million. The
   allowed margin is half that rounding step, clamped to between 2% and 10%
   of the real figure. The 10% cap stops "India has 1 billion people"
   passing on a rounding technicality.
2. "over X" / "under X" are checked as bounds; "about X" uses the margin.
3. Only a measured estimate can make a claim WRONG. When the only figure
   is a projection, a mismatch is UNCONFIRMED, and the latest measured
   figure is shown alongside (projections can be out of date: WPP 2024
   put Canada's 2026 population below its measured 2025 population).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from ..data.models import Figure
from ..data.population import Population

MIN_MARGIN = 0.02
MAX_MARGIN = 0.10
# Census counts differ from population estimates by definition (Canada 2021:
# census 36,991,981 vs World Bank estimate 38,239,864, 3.3% apart). A census
# claim within 5% is UNCONFIRMED, not WRONG (approved 2026-11-24).
CENSUS_MARGIN = 0.05


class Verdict(Enum):
    CORRECT = "correct"
    WRONG = "wrong"
    UNCONFIRMED = "unconfirmed"
    CANT_VERIFY = "can't verify"


class Comparator(Enum):
    ABOUT = "about"   # also exact statements: "Canada has 41.7 million people"
    OVER = "over"     # "over", "more than", "at least"
    UNDER = "under"   # "under", "fewer than", "less than"


@dataclass(frozen=True)
class PopulationClaim:
    country: str
    value: float                       # the claimed number of people
    year: int | None = None            # None: "now", checked against latest estimate
    comparator: Comparator = Comparator.ABOUT
    written: str | None = None         # as it appeared, e.g. "41.7 million"
    census: bool = False               # the text cites a census count


@dataclass(frozen=True)
class PopulationResult:
    verdict: Verdict
    claim: PopulationClaim
    figure: Figure | None              # the figure the claim was judged against
    latest_estimate: Figure | None     # extra context for UNCONFIRMED
    message: str


def rounding_step(value: float, written: str | None = None) -> float:
    """The rounding step a number implies: 41.7 million -> 100,000."""
    if written:
        match = re.search(r"\d[\d,]*(?:\.\d+)?", written)
        if match:
            try:
                mantissa = Decimal(match.group().replace(",", ""))
            except InvalidOperation:
                mantissa = None
            if mantissa:
                # "40.0" keeps its written precision; "40" drops trailing zeros.
                exp = (mantissa.as_tuple().exponent if "." in match.group()
                       else mantissa.normalize().as_tuple().exponent)
                return float(Decimal(10) ** exp) * (value / float(mantissa))
    return float(Decimal(10) ** Decimal(str(value)).normalize().as_tuple().exponent)


def margin(claim: PopulationClaim, actual: float) -> float:
    """Allowed absolute difference: half the rounding step, clamped 2%-10%."""
    half_step = rounding_step(claim.value, claim.written) / 2
    return min(max(half_step, MIN_MARGIN * actual), MAX_MARGIN * actual)


def matches(claim: PopulationClaim, actual: float) -> bool:
    if claim.comparator is Comparator.OVER:
        return actual > claim.value
    if claim.comparator is Comparator.UNDER:
        return actual < claim.value
    return abs(actual - claim.value) <= margin(claim, actual)


def _people(n: float) -> str:
    return f"{n:,.0f}"


def _describe(f: Figure) -> str:
    label = "projection" if f.kind == "projection" else "estimate"
    return f"{_people(f.value)} ({f.source.split(',')[0]} {f.year} {label})"


def check_population(claim: PopulationClaim, population: Population) -> PopulationResult:
    lookup = population.lookup(claim.country, claim.year)
    if lookup.figure is None:
        return PopulationResult(Verdict.CANT_VERIFY, claim, None, None,
                                f"Can't verify: {lookup.note}.")

    f = lookup.figure
    name = "The world" if lookup.country.iso3 == "WLD" else lookup.country.name
    owner = f"{name}'" if name.endswith("s") else f"{name}'s"   # "United States'"
    stated = claim.written or _people(claim.value)
    ok = matches(claim, f.value)
    off = abs(f.value - claim.value) / f.value

    if f.kind == "estimate":
        if ok:
            return PopulationResult(Verdict.CORRECT, claim, f, None,
                                    f"Correct: {owner} population is {_describe(f)}.")
        if claim.census and off <= CENSUS_MARGIN:
            return PopulationResult(
                Verdict.UNCONFIRMED, claim, f, None,
                f"Unconfirmed: this cites a census count, which differs from population "
                f"estimates (estimates adjust for people a census misses). {owner} "
                f"population is {_describe(f)}, {off:.1%} from {stated}.")
        return PopulationResult(
            Verdict.WRONG, claim, f, None,
            f"Wrong: {owner} population is {_describe(f)}, not {stated} ({off:.1%} off).")

    # Only a projection exists for this year.
    if ok:
        return PopulationResult(Verdict.CORRECT, claim, f, None,
                                f"Correct: consistent with {_describe(f)}.")
    latest = population.lookup(claim.country).figure
    latest = latest if latest and latest.kind == "estimate" else None
    message = f"Unconfirmed: differs from {_describe(f)}."
    if latest:
        agrees = "which matches this claim" if matches(claim, latest.value) else \
                 "which also differs"
        message += f" The latest measured figure is {_describe(latest)}, {agrees}."
    return PopulationResult(Verdict.UNCONFIRMED, claim, f, latest, message)
