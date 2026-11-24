"""Paragraph in, verdicts out: the whole of Hallucinope in one function.

    check_text(text, population) -> Report

Each claim found in the text is sent to its checker (populations to the
verdict rules, conversions to the units engine) and comes back with a
verdict, a plain-English message, the figure it was judged against (its
receipt), and its position in the text for highlighting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .checks.population_claims import Verdict, check_population
from .data.models import Figure
from .data.population import Population
from .extract.claims import Claim, extract
from .extract.countries import CountryIndex
from .extract.numbers import NumberSpan
from .llm.base import JsonModel
from .units.convert import IncompatibleUnitsError, check_conversion


@dataclass(frozen=True)
class CheckedClaim:
    claim: Claim
    verdict: Verdict
    message: str
    figure: Figure | None = None           # the receipt, for population claims
    latest_estimate: Figure | None = None  # extra context when UNCONFIRMED

    @property
    def start(self) -> int:
        return self.claim.start

    @property
    def end(self) -> int:
        return self.claim.end


@dataclass
class Report:
    text: str
    checked: list[CheckedClaim] = field(default_factory=list)
    unchecked: list[NumberSpan] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # data or model problems

    def count(self, verdict: Verdict) -> int:
        return sum(1 for c in self.checked if c.verdict is verdict)


def _check_conversion(claim: Claim) -> CheckedClaim:
    c = claim.conversion
    try:
        result = check_conversion(c.value, c.unit, c.stated_value, c.stated_unit)
    except IncompatibleUnitsError as exc:
        return CheckedClaim(claim, Verdict.CANT_VERIFY, f"Can't verify: {exc}.")
    message = result.message[0].upper() + result.message[1:] + "."
    return CheckedClaim(claim, Verdict.CORRECT if result.correct else Verdict.WRONG, message)


def check_text(text: str, population: Population, countries: CountryIndex | None = None,
               model: JsonModel | None = None) -> Report:
    countries = countries or CountryIndex.from_population(population)
    extraction = extract(text, countries, model)
    report = Report(text, unchecked=extraction.unchecked, notes=list(population.notes))
    report.notes += extraction.model_errors[:1]  # one is enough; the rest repeat it
    for claim in extraction.claims:
        if claim.kind == "conversion":
            report.checked.append(_check_conversion(claim))
        else:
            r = check_population(claim.population, population)
            report.checked.append(CheckedClaim(claim, r.verdict, r.message, r.figure,
                                               r.latest_estimate))
    return report
