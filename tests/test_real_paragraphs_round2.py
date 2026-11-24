"""Regression tests from the second batch of real ChatGPT paragraphs (2026-11-24).

These found 5 false alarms (red WRONG on true numbers) and 1 missed error:
  03 Japan      years attached to the wrong number ("103.4 million in 1970" -> 1960)
  04 provinces  Quebec's and BC's populations checked as Canada's
  01 Canada     a true 2021 census count marked WRONG (census vs estimate)
  09            "5.2 pounds" read as money, so a wrong conversion was missed

Figures are the real World Bank/UN values shown in the 2026-11-24 run, except
Japan 1970 and 2000, which are close approximations (marked below).
"""

from datetime import date

import pytest

from hallucinope.checks.population_claims import Verdict
from hallucinope.data import un, worldbank
from hallucinope.data.models import Country, PopulationData, Series
from hallucinope.data.population import Population
from hallucinope.report import check_text

DAY = date(2026, 11, 24)

P01 = ("Canada's population has grown steadily in recent years. In the 2021 Census, Canada "
       "recorded 36,991,981 people, while Statistics Canada estimated the population at "
       "40,097,761 on July 1, 2023. By July 1, 2026, the estimate had reached 41,798,407 "
       "people, showing substantial growth over five years.")
P03 = ("Japan's population increased for several decades before beginning a sustained "
       "decline. It had about 93.2 million people in 1960 and 103.4 million in 1970. The "
       "population reached approximately 116.8 million in 1980 and 126.8 million in 2000, "
       "before peaking at about 128.1 million in 2010. By 2025, it had fallen to roughly "
       "123.4 million, reflecting the country's ageing population and low birth rate.")
P04 = ("Ontario is Canada's most populous province, with an estimated 16,262,121 residents "
       "on July 1, 2026. Quebec had approximately 9,067,114 people on the same date, making it "
       "the second most populous province. British Columbia had about 5,710,598 residents. "
       "Ontario therefore had almost twice the population of Quebec and nearly three times "
       "the population of British Columbia.")
P08 = ("The populations of five countries vary greatly. India has approximately 1.46 billion "
       "people, China has about 1.41 billion, the United States has around 347 million, "
       "Indonesia has roughly 320 million, and Brazil has approximately 250 million. These "
       "figures illustrate how a small group of countries accounts for a substantial share "
       "of the world's population.")
P09 = ("A short conversion check: 5 kilometres is equal to 3.11 miles, 2 kilograms is equal "
       "to 5.2 pounds, 20°C is equal to 68°F, and 100°F is equal to 40°C.")


def _wb(iso3, name, values):
    s = Series(Country(iso3, "", name))
    for year, value in values.items():
        s.figures[year] = worldbank.make_figure(iso3, year, value, DAY)
    return s


@pytest.fixture(scope="module")
def population():
    wb = PopulationData({
        "CAN": _wb("CAN", "Canada", {2021: 38_239_864, 2023: 40_049_088, 2025: 41_651_653}),
        "JPN": _wb("JPN", "Japan", {1960: 93_216_000,
                                    1970: 104_345_000,      # approximation
                                    1980: 116_807_000,
                                    2000: 126_843_000,      # approximation
                                    2010: 128_070_000, 2025: 123_366_734}),
        "IND": _wb("IND", "India", {2025: 1_463_865_525}),
        "CHN": _wb("CHN", "China", {2025: 1_406_585_000}),
        "USA": _wb("USA", "United States", {2025: 341_784_857}),
        "IDN": _wb("IDN", "Indonesia", {2025: 285_721_236}),
        "BRA": _wb("BRA", "Brazil", {2025: 212_812_405}),
    })
    can = Series(Country("CAN", "", "Canada"))
    can.figures[2026] = un.make_figure("CAN", 2026, 40_467_728, DAY, "projection")
    return Population(wb, PopulationData({"CAN": can}))


def verdicts(text, population):
    return [(c.claim.text, c.verdict) for c in check_text(text, population).checked]


def test_01_census_count_is_amber_not_red(population):
    report = check_text(P01, population)
    assert [(c.claim.text, c.verdict) for c in report.checked] == [
        ("36,991,981", Verdict.UNCONFIRMED),   # census vs estimate, 3.3% apart
        ("40,097,761", Verdict.CORRECT),       # July 1, 2023 -> 2023, not 2021
        ("41,798,407", Verdict.UNCONFIRMED),   # 2026: projection only; matches 2025 estimate
    ]
    assert "census count" in report.checked[0].message


def test_03_japan_years_attach_to_the_right_numbers(population):
    assert verdicts(P03, population) == [(t, Verdict.CORRECT) for t in (
        "93.2 million", "103.4 million", "116.8 million", "126.8 million",
        "128.1 million", "123.4 million")]


def test_04_provinces_are_not_checked_as_canada(population):
    report = check_text(P04, population)
    assert report.checked == []
    assert {s.text for s in report.unchecked} >= {"16,262,121", "9,067,114", "5,710,598"}


def test_08_planted_errors_caught_and_nothing_else(population):
    assert verdicts(P08, population) == [
        ("1.46 billion", Verdict.CORRECT), ("1.41 billion", Verdict.CORRECT),
        ("347 million", Verdict.CORRECT), ("320 million", Verdict.WRONG),
        ("250 million", Verdict.WRONG)]


def test_08_possessive_for_names_ending_in_s(population):
    msg = check_text(P08, population).checked[2].message
    assert msg.startswith("Correct: United States' population")


def test_09_both_planted_conversion_errors_caught(population):
    report = check_text(P09, population)
    assert [(c.claim.text.split(" is")[0], c.verdict) for c in report.checked] == [
        ("5 kilometres", Verdict.CORRECT), ("2 kilograms", Verdict.WRONG),
        ("20°C", Verdict.CORRECT), ("100°F", Verdict.WRONG)]
