"""Regression tests for the bugs round 2 of the benchmark exposed (2026-11-24).

  1. "South America" was read as "America" (the USA), so Chile's figures were
     checked against the United States.
  2. "...by 2000. In 2020..." was read as "2000 inches", losing the year, so
     Colombia's and Cuba's 2000 figures were checked against 1960.
  3. "US fluid ounces" and "50 L" were not recognised as units.
"""

import pytest

from hallucinope.data.models import ALIASES
from hallucinope.extract.claims import extract
from hallucinope.extract.countries import CountryIndex
from hallucinope.extract.numbers import find_numbers

CHILE = ("Chile had a population of approximately 19.86 million in 2025, making it one of "
         "the more populous countries in South America. In 1960, its population was "
         "approximately 7.65 million, reflecting substantial growth over 65 years. By 2000, "
         "the population had reached approximately 15.4 million, and by 2020 it was around "
         "19.3 million.")
COLOMBIA = ("Colombia had an estimated population of approximately 53.4 million in 2025. Its "
            "population was around 16.0 million in 1960, increasing to approximately 39.8 "
            "million by 2000. In 2020, Colombia had approximately 50.9 million inhabitants.")
CUBA = ("Cuba had an estimated population of approximately 10.9 million in 2025. Its "
        "population was around 7.1 million in 1960, before increasing to approximately 11.1 "
        "million by 2000. In 2020, Cuba's population was approximately 11.3 million.")


@pytest.fixture(scope="module")
def countries():
    names = {"chile": "CHL", "colombia": "COL", "cuba": "CUB", "united states": "USA"}
    codes = {c: c for c in names.values()}
    for alias, iso3 in ALIASES.items():
        if len(alias) > 3:
            names.setdefault(alias, iso3)
        else:
            codes.setdefault(alias.upper(), iso3)
    return CountryIndex(names, codes)


def labels(text, countries):
    return [(c.text, c.population.country, c.population.year)
            for c in extract(text, countries).claims]


def test_south_america_is_not_the_usa(countries):
    assert [m.iso3 for m in countries.mentions(CHILE)] == ["CHL"]
    assert labels(CHILE, countries) == [
        ("19.86 million", "CHL", 2025), ("7.65 million", "CHL", 1960),
        ("15.4 million", "CHL", 2000), ("19.3 million", "CHL", 2020)]


@pytest.mark.parametrize("text", ["the USA and America", "people in America"])
def test_america_alone_is_still_the_usa(countries, text):
    assert countries.mentions(text)[-1].iso3 == "USA"


@pytest.mark.parametrize("text", ["Latin America", "North America", "Central America",
                                  "South-America"])
def test_continents_are_not_the_usa(countries, text):
    assert countries.mentions(text) == []


def test_year_before_a_full_stop_is_not_inches(countries):
    assert [s.kind for s in find_numbers("by 2000. In 2020, it grew")] == ["year", "year"]
    assert ("39.8 million", "COL", 2000) in labels(COLOMBIA, countries)
    assert ("11.1 million", "CUB", 2000) in labels(CUBA, countries)


def test_us_fluid_ounces_and_capital_L(countries):
    r = extract("Drinking 500 mL (16.91 US fluid ounces) of water. A 50 L (13.21 US gallon) "
                "fuel tank.", countries)
    conv = [(c.conversion.value, c.conversion.stated_value) for c in r.claims]
    assert conv == [(500, 16.91), (50, 13.21)]
