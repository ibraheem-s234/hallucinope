"""Tests for claim extraction: numbers, comparisons, countries, grounding."""

import pytest

from hallucinope.checks.population_claims import Comparator
from hallucinope.data.models import ALIASES
from hallucinope.eval.extraction import load_cases, score
from hallucinope.extract.claims import extract
from hallucinope.extract.comparators import comparator_before
from hallucinope.extract.countries import CountryIndex
from hallucinope.extract.numbers import find_numbers
from hallucinope.llm.base import LLMError

NAMES = {"Canada": "CAN", "France": "FRA", "India": "IND", "Japan": "JPN", "Nigeria": "NGA",
         "Niger": "NER", "Brazil": "BRA", "Germany": "DEU", "Mexico": "MEX", "China": "CHN",
         "Egypt, Arab Rep.": "EGY", "United Kingdom": "GBR", "Australia": "AUS", "Kenya": "KEN",
         "Korea, Rep.": "KOR", "Iceland": "ISL", "Ethiopia": "ETH", "United States": "USA"}


@pytest.fixture(scope="module")
def countries():
    names = {n.lower(): c for n, c in NAMES.items()}
    codes = {c: c for c in names.values()}
    for alias, iso3 in ALIASES.items():
        if len(alias) > 3:
            names.setdefault(alias, iso3)
        else:
            codes.setdefault(alias.upper(), iso3)
    return CountryIndex(names, codes)


class FakeModel:
    name = "fake"

    def __init__(self, *answers, error=None):
        self.answers, self.error, self.prompts, self.schemas = list(answers), error, [], []

    def complete_json(self, system, user, schema):
        self.prompts.append(user)
        self.schemas.append(schema)
        if self.error:
            raise self.error
        return self.answers.pop(0)


# --- Finding numbers --------------------------------------------------------

@pytest.mark.parametrize("text, found, kind, value", [
    ("roughly 41 million people", "41 million", "count", 41e6),
    ("41,651,653 people", "41,651,653", "count", 41_651_653),
    ("over 1.4 billion", "1.4 billion", "count", 1.4e9),
    ("40M users", "40M", "count", 40e6),
    ("260 km away", "260 km", "quantity", 260),
    ("it was 20°C", "20°C", "quantity", 20),
    ("60 miles per hour", "60 miles per hour", "quantity", 60),
    ("100 g of sugar", "100 g", "quantity", 100),
    ("grew 3.5%", "3.5%", "percent", 3.5),
    ("4 per cent", "4 per cent", "percent", 4),
    ("$2 billion", "$2 billion", "money", 2e9),
    ("40 dollars", "40 dollars", "money", 40),
    ("in 2025", "2025", "year", 2025),
])
def test_find_numbers(text, found, kind, value):
    span = find_numbers(text)[0]
    assert (span.text, span.kind) == (found, kind)
    assert span.value == pytest.approx(value)
    assert text[span.start:span.end] == found


def test_english_words_are_not_read_as_units():
    spans = find_numbers("Canada had 41 million in 2025 and 3 t of hay")
    assert [s.kind for s in spans] == ["count", "year", "count"]   # "in" is not inches


def test_glued_ambiguous_unit_is_read():
    assert find_numbers("a 12in pizza")[0].kind == "quantity"


# --- Comparison words -------------------------------------------------------

@pytest.mark.parametrize("before, expected", [
    ("roughly ", Comparator.ABOUT), ("has ", Comparator.ABOUT),
    ("more than ", Comparator.OVER), ("will pass ", Comparator.OVER),
    ("a population of over ", Comparator.OVER), ("exceeded ", Comparator.OVER),
    ("fewer than ", Comparator.UNDER), ("fell below ", Comparator.UNDER),
    ("just under ", Comparator.UNDER), ("Moreover ", Comparator.ABOUT),
])
def test_comparator_before(before, expected):
    text = before + "40 million"
    assert comparator_before(text, len(before)) is expected


# --- Country mentions -------------------------------------------------------

def test_mentions_ignore_lowercase_codes(countries):
    found = countries.mentions("Let us see if we can. The US and Canada.")
    assert [m.iso3 for m in found] == ["USA", "CAN"]


def test_longest_name_wins(countries):
    assert [m.iso3 for m in countries.mentions("Nigeria and Niger")] == ["NGA", "NER"]
    assert countries.mentions("South Korea")[0].text == "South Korea"


# --- Extraction, rules only -------------------------------------------------

def test_subject_before_number_wins(countries):
    r = extract("France had a population of 67 million, while India's population "
                "exceeded 1.4 billion.", countries)
    assert [(c.text, c.population.country) for c in r.claims] == [
        ("67 million", "FRA"), ("1.4 billion", "IND")]


def test_population_topic_continues_to_next_sentence(countries):
    r = extract("Canada has 41 million people. By 2026 the country will pass 42 million.",
                countries)
    second = r.claims[1].population
    assert (second.country, second.year, second.comparator) == ("CAN", 2026, Comparator.OVER)


def test_other_plural_nouns_are_not_population(countries):
    r = extract("Brazil had 203 million residents, and 6 million tourists visited.", countries)
    assert [c.text for c in r.claims] == ["203 million"]
    assert [s.text for s in r.unchecked] == ["6 million"]


def test_conversion_pairs(countries):
    r = extract("It is 260 km (about 160 miles), and it was 30 °C (86 °F).", countries)
    conv = [c.conversion for c in r.claims]
    assert [(c.value, c.unit, c.stated_value, c.stated_unit) for c in conv] == [
        (260, "km", 160, "miles"), (30, "°C", 86, "°F")]


def test_unchecked_summary(countries):
    r = extract("Mexico's population is under 100 million; GDP grew 3% to $2 billion "
                "over 7.7 million square kilometres in 2023, with 12 cities.", countries)
    assert [s.text for s in r.unchecked] == ["3%", "$2 billion", "7.7 million square kilometres"]


def test_no_country_in_text_means_no_claim(countries):
    assert extract("The town has 40,000 residents.", countries).claims == []


# --- The model, and the checks on its answers -------------------------------

# "the largest city" isn't in the place list, so only the model can tell.
TEXT = "Canada has 41 million people. Meanwhile 3 million live in the largest city."
COUNTRY = "a country"


def label(describes=COUNTRY, country="Canada", year=None):
    return {"describes": describes, "country": country, "year": year}


def test_model_sees_the_number_marked(countries):
    model = FakeModel(label(), label())
    extract(TEXT, countries, model)
    assert "[[3 million]] live in the largest city" in model.prompts[1]


@pytest.mark.parametrize("text", [
    "Quebec had approximately 9,067,114 people.",
    "Ontario is Canada's most populous province, with 16,262,121 residents.",
    "About 3 million people live in Toronto, Canada's largest city.",
    "Germany has 84 million people. Its capital, Berlin, has about 3.8 million.",
])
def test_provinces_and_cities_are_not_checked_as_countries(countries, text):
    claims = extract(text, countries).claims
    assert all(c.text not in ("9,067,114", "16,262,121", "3 million", "3.8 million")
               for c in claims)


@pytest.mark.parametrize("text, year", [
    ("Japan had 93.2 million people in 1960 and 103.4 million in 1970.", 1970),
    ("By 2025, Japan had fallen to roughly 123.4 million people.", 2025),
    ("Canada estimated its population at 40,097,761 on July 1, 2023.", 2023),
    ("South Korea has 52 million citizens, but 250,000 babies were born in 2023.", None),
])
def test_year_rules(countries, text, year):
    claim = [c for c in extract(text, countries).claims
             if c.text in ("103.4 million", "123.4 million", "40,097,761", "52 million")][0]
    assert claim.population.year == year


def test_pounds_without_pound_sign_are_weight(countries):
    r = extract("2 kilograms is equal to 5.2 pounds.", countries)
    assert r.claims[0].kind == "conversion"


def test_model_can_only_choose_countries_and_years_in_the_text(countries):
    model = FakeModel(label(year=2020))
    extract("In 2020, Canada and the US had 41 million people.", countries, model)
    props = model.schemas[0]["properties"]
    assert props["country"]["enum"] == ["Canada", "US", None]
    assert props["year"]["enum"] == [2020, None]
    assert props["describes"]["enum"] == ["a country", "a city or region", "something else"]


def test_accepted_model_label(countries):
    r = extract(TEXT, countries, FakeModel(label(), label(describes="a city or region")))
    assert [(c.text, c.labelled_by) for c in r.claims] == [("41 million", "model")]


@pytest.mark.parametrize("describes", ["a city or region", "something else"])
def test_model_can_remove_a_claim_but_not_add_one(countries, describes):
    r = extract(TEXT, countries, FakeModel(label(), label(describes=describes)))
    assert [c.text for c in r.claims] == ["41 million"]
    assert "3 million" in [s.text for s in r.unchecked]


@pytest.mark.parametrize("answer", [label(country="France"),     # not in text
                                    label(year=1999),            # year not in text
                                    label(country=None)])        # "a country", but which?
def test_ungrounded_model_answer_is_rejected(countries, answer):
    r = extract("Canada has 41 million people.", countries, FakeModel(answer))
    claim = r.claims[0]
    assert claim.population.country == "CAN" and claim.population.year is None
    assert claim.labelled_by == "rules (model answer rejected)"


def test_model_failure_falls_back_to_rules(countries):
    r = extract("Canada has 41 million people.", countries,
                FakeModel(error=LLMError("[LLM:Ollama] can't reach Ollama")))
    assert r.claims[0].labelled_by == "rules (model unavailable)"
    assert r.model_errors


# --- The scoring command ----------------------------------------------------

def test_rules_baseline_on_the_test_set(countries):
    s = score("rules only", load_cases(), countries)
    assert s.expected == 19 and s.conversions_found == s.conversions_expected == 3
    assert s.correct == 19            # regression guard for the rules
    assert s.false_positives == 0     # city traps caught by the place list


# --- v1.1: conversion pairing (benchmark findings, 2026-11-24) ---------------

@pytest.mark.parametrize("text", [
    "A room measuring 5 m by 4 m has a floor area of 20 m².",
    "Add 30 g of melted butter and 15 g of sugar.",
    "Use 250 g of flour, 150 g of sugar and 120 mL of milk.",
    "Water freezes at 0°C and boils at approximately 100°C.",
    "A person weighing 190 lb, while someone weighing 5 kg is a baby.",
    "One square metre is 10.764 square feet, meaning that a 100 m² flat is large.",
])
def test_lists_sizes_and_contrasts_are_not_conversions(countries, text):
    assert [c for c in extract(text, countries).claims if c.kind == "conversion"] == []


@pytest.mark.parametrize("text, value, stated", [
    ("90 km/h is equivalent to approximately 55.92 mph.", 90, 55.92),
    ("If an oven is set to 350°F, the equivalent temperature is approximately 177°C.",
     350, 177),
    ("A weather forecast showing 68°F indicates a temperature of approximately 20°C.", 68, 20),
    ("A person weighing 70 kg has a weight of approximately 154 lb.", 70, 154),
    ("A 100 m² apartment has approximately 1,076.4 square feet.", 100, 1076.4),
    ("2 litres of water is equivalent to approximately 0.53 US gallons.", 2, 0.53),
    ("A measuring jug containing 250 mL of liquid holds approximately 1.06 US cups.", 250, 1.06),
    ("It is 260 km (about 160 miles) away.", 260, 160),
])
def test_conversions_with_longer_wording_are_found(countries, text, value, stated):
    conv = [c.conversion for c in extract(text, countries).claims if c.kind == "conversion"]
    assert [(c.value, c.stated_value) for c in conv] == [(value, stated)]


def test_people_per_area_is_a_rate_not_a_population(countries):
    r = extract("India has 1.46 billion people, about 1,193 people per square "
                "kilometre.", countries)
    assert [c.text for c in r.claims] == ["1.46 billion"]
