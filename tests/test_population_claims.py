"""Tests for population verdicts.

Canada's figures are the real ones from the 2026-11-16/18 downloads:
World Bank 2025 estimate 41,651,653; UN WPP 2024 projection for 2026
40,467,728. Every row of the approved verdict table is a test here.
"""

from datetime import date

import pytest

from hallucinope.checks.population_claims import (
    Comparator, PopulationClaim, Verdict, check_population, rounding_step)
from hallucinope.data import un, worldbank
from hallucinope.data.models import Country, PopulationData, Series
from hallucinope.data.population import Population

DAY = date(2026, 11, 18)
CANADA = Country("CAN", "CA", "Canada")
INDIA = Country("IND", "IN", "India")


def _series(country, figures):
    s = Series(country)
    for f in figures:
        s.figures[f.year] = f
    return s


@pytest.fixture
def pop():
    wb = PopulationData({
        "CAN": _series(CANADA, [worldbank.make_figure("CAN", 2025, 41_651_653, DAY)]),
        "IND": _series(INDIA, [worldbank.make_figure("IND", 2025, 1_450_000_000, DAY)]),  # synthetic
    })
    unp = PopulationData({
        "CAN": _series(CANADA, [un.make_figure("CAN", 2026, 40_467_728, DAY, "projection")]),
    })
    return Population(wb, unp)


def claim(value, written=None, year=None, comparator=Comparator.ABOUT, country="Canada"):
    return PopulationClaim(country, value, year, comparator, written)


# --- The approved table, row by row ---------------------------------------

@pytest.mark.parametrize("c, verdict", [
    (claim(40_000_000, "about 40 million"), Verdict.CORRECT),
    (claim(41_500_000, "41.5 million"), Verdict.CORRECT),
    (claim(38_000_000, "38 million"), Verdict.WRONG),
    (claim(40_000_000, "over 40 million", comparator=Comparator.OVER), Verdict.CORRECT),
    (claim(40_000_000, "under 40 million", comparator=Comparator.UNDER), Verdict.WRONG),
    (claim(40_500_000, "40.5 million", year=2026), Verdict.CORRECT),
    (claim(41_700_000, "41.7 million", year=2026), Verdict.UNCONFIRMED),
])
def test_approved_table(pop, c, verdict):
    assert check_population(c, pop).verdict is verdict


# --- What each verdict tells the reader -----------------------------------

def test_wrong_shows_real_figure_and_source(pop):
    r = check_population(claim(38_000_000, "38 million"), pop)
    assert "41,651,653" in r.message and "World Bank 2025 estimate" in r.message
    assert "not 38 million" in r.message and "8.8% off" in r.message


def test_projection_match_is_labelled_as_projection(pop):
    r = check_population(claim(40_500_000, "40.5 million", year=2026), pop)
    assert "UN" in r.message or "United Nations" in r.message
    assert "projection" in r.message and r.figure.kind == "projection"


def test_unconfirmed_shows_projection_and_latest_estimate(pop):
    r = check_population(claim(41_700_000, "41.7 million", year=2026), pop)
    assert "40,467,728" in r.message and "41,651,653" in r.message
    assert "matches this claim" in r.message
    assert r.latest_estimate.year == 2025


def test_projection_can_never_produce_wrong(pop):
    r = check_population(claim(10_000_000, "10 million", year=2026), pop)
    assert r.verdict is Verdict.UNCONFIRMED
    assert "also differs" in r.message


def test_no_data_is_cant_verify(pop):
    assert check_population(claim(30_000_000, year=1950), pop).verdict is Verdict.CANT_VERIFY
    assert check_population(claim(1, country="Atlantis"), pop).verdict is Verdict.CANT_VERIFY


# --- The margin rule -------------------------------------------------------

def test_ten_percent_cap_blocks_rounding_technicality(pop):
    # 1.45 billion rounds to "1 billion" at one significant figure, but
    # that is 31% off and the 10% cap rejects it.
    r = check_population(claim(1_000_000_000, "1 billion", country="India"), pop)
    assert r.verdict is Verdict.WRONG


@pytest.mark.parametrize("value, written, step", [
    (40_000_000, "40 million", 10_000_000),
    (41_700_000, "41.7 million", 100_000),
    (40_000_000, "40.0 million", 100_000),     # written precision is kept
    (41_651_653, "41,651,653", 1),
    (40_000_000, None, 10_000_000),            # inferred from the number itself
    (41_700_000, None, 100_000),
])
def test_rounding_step(value, written, step):
    assert rounding_step(value, written) == pytest.approx(step)


def test_precise_number_still_gets_two_percent_minimum(pop):
    # A number written to the person implies a margin of +/-0.5 people; the
    # 2% floor forgives a precise figure from a slightly different date.
    assert rounding_step(41_234_567, "41,234,567") == 1
    assert check_population(claim(41_234_567, "41,234,567"), pop).verdict is Verdict.CORRECT
