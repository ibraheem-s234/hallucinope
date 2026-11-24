"""Regression tests from real ChatGPT paragraphs (2026-11-23).

These exposed the "world population" bug: world figures were attributed to
the last country mentioned, and a true UN projection ("10.3 billion by the
mid-2080s") was marked WRONG as China's population. They must never be again.

India and China use the real World Bank 2025 figures from the 2026-11-16
download. World figures are close approximations of the real WB/UN values.
"""

from datetime import date

import pytest

from hallucinope.checks.population_claims import Verdict
from hallucinope.data import un, worldbank
from hallucinope.data.models import Country, PopulationData, Series
from hallucinope.data.population import Population
from hallucinope.report import check_text

DAY = date(2026, 11, 16)
WORLD, INDIA, CHINA = Country("WLD", "", "World"), Country("IND", "IN", "India"), \
    Country("CHN", "CN", "China")

NORMAL = (
    "According to the United Nations, the world's population is estimated to be "
    "approximately 8.3 billion people in 2026. India is currently the most populated "
    "country, with approximately 1.48 billion people, followed by China, with approximately "
    "1.41 billion. The global population continues to increase, although its growth rate "
    "has slowed significantly compared to previous decades. In 1950, the world's population "
    "was approximately 2.5 billion, meaning it has more than tripled in just over 75 years. "
    "Scientists predict that the global population will reach approximately 10.3 billion by "
    "the mid-2080s before gradually declining.")

DELIBERATE = (
    "According to international population researchers, the world's population is estimated "
    "to be approximately 9.7 billion people in 2026. China is currently the most populated "
    "country, with approximately 1.8 billion people, followed by India, with approximately "
    "1.2 billion. The global population is increasing at a faster rate than ever before, with "
    "population growth reaching approximately 3.5% annually. In 1950, the world's population "
    "was approximately 4.5 billion, meaning it has more than doubled in just over 75 years. "
    "Scientists predict that the global population will reach approximately 15 billion by "
    "2050 before gradually declining.")


def _series(country, figures):
    s = Series(country)
    for f in figures:
        s.figures[f.year] = f
    return s


@pytest.fixture(scope="module")
def population():
    wb = PopulationData({
        "WLD": _series(WORLD, [worldbank.make_figure("WLD", 2025, 8_230_000_000, DAY)]),
        "IND": _series(INDIA, [worldbank.make_figure("IND", 2025, 1_463_865_525, DAY)]),
        "CHN": _series(CHINA, [worldbank.make_figure("CHN", 2025, 1_406_585_000, DAY)]),
    })
    unp = PopulationData({"WLD": _series(WORLD, [
        un.make_figure("WLD", 1950, 2_493_000_000, DAY, "estimate"),
        un.make_figure("WLD", 2026, 8_300_000_000, DAY, "projection"),
        un.make_figure("WLD", 2050, 9_660_000_000, DAY, "projection"),
        un.make_figure("WLD", 2085, 10_290_000_000, DAY, "projection"),
    ])})
    return Population(wb, unp)


def verdicts(report):
    return [(c.claim.text, c.claim.population.country, c.verdict) for c in report.checked]


def test_normal_paragraph_is_all_correct(population):
    report = check_text(NORMAL, population)
    assert verdicts(report) == [
        ("8.3 billion", "WLD", Verdict.CORRECT),    # UN 2026 projection
        ("1.48 billion", "IND", Verdict.CORRECT),
        ("1.41 billion", "CHN", Verdict.CORRECT),
        ("2.5 billion", "WLD", Verdict.CORRECT),    # UN 1950 estimate
        ("10.3 billion", "WLD", Verdict.CORRECT),   # UN projection for the mid-2080s
    ]


def test_true_projection_is_never_marked_wrong(population):
    report = check_text(NORMAL, population)
    assert report.count(Verdict.WRONG) == 0


def test_deliberate_errors_are_caught(population):
    report = check_text(DELIBERATE, population)
    assert verdicts(report) == [
        ("9.7 billion", "WLD", Verdict.UNCONFIRMED),  # vs 2026 projection: amber
        ("1.8 billion", "CHN", Verdict.WRONG),
        ("1.2 billion", "IND", Verdict.WRONG),
        ("4.5 billion", "WLD", Verdict.WRONG),        # 1950 is a measured estimate
        ("15 billion", "WLD", Verdict.UNCONFIRMED),   # vs 2050 projection: amber
    ]
    assert [s.text for s in report.unchecked] == ["3.5%", "75 years"]


def test_world_wording(population):
    report = check_text(DELIBERATE, population)
    assert report.checked[3].message.startswith("Wrong: The world's population is 2,493,000,000")


@pytest.mark.parametrize("text, year", [("by the mid-2080s", 2085), ("in the 2080s", 2085),
                                        ("the early 2030s", 2032), ("the late 1990s", 1998)])
def test_decades_become_years(text, year):
    from hallucinope.extract.numbers import find_numbers
    span = find_numbers(text)[0]
    assert (span.kind, span.value) == ("year", year)
