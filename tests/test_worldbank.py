"""Tests for the World Bank source, run offline against a fake fetcher.

The sample responses copy the World Bank API's JSON *format*, but the
population values are synthetic round numbers, not real figures.
"""

from datetime import date

import pytest

from hallucinope.data.models import DataSourceError
from hallucinope.data.worldbank import fetch_population

COUNTRIES = [
    {"page": 1, "pages": 1, "per_page": "400", "total": 4},
    [
        {"id": "CAN", "iso2Code": "CA", "name": "Canada", "region": {"value": "North America"}},
        {"id": "FRA", "iso2Code": "FR", "name": "France", "region": {"value": "Europe & Central Asia"}},
        {"id": "USA", "iso2Code": "US", "name": "United States", "region": {"value": "North America"}},
        {"id": "WLD", "iso2Code": "1W", "name": "World", "region": {"value": "Aggregates"}},
        {"id": "EMU", "iso2Code": "XC", "name": "Euro area", "region": {"value": "Aggregates"}},
    ],
]


def _row(iso3, name, year, value):
    return {"indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
            "country": {"id": iso3[:2], "value": name}, "countryiso3code": iso3,
            "date": str(year), "value": value, "unit": "", "obs_status": "", "decimal": 0}


# Two pages, to prove pagination works.
POP_PAGE_1 = [
    {"page": 1, "pages": 2, "per_page": 20000, "total": 7, "lastupdated": "2026-07-01"},
    [_row("CAN", "Canada", 2025, 40_000_000), _row("CAN", "Canada", 2024, 39_000_000),
     _row("FRA", "France", 2025, None),            # missing latest year
     _row("FRA", "France", 2024, 68_000_000)],
]
POP_PAGE_2 = [
    {"page": 2, "pages": 2, "per_page": 20000, "total": 7, "lastupdated": "2026-07-01"},
    [_row("USA", "United States", 2025, 340_000_000),
     _row("WLD", "World", 2025, 8_000_000_000),    # the World: kept
     _row("EMU", "Euro area", 2025, 350_000_000),  # other aggregate: ignored
     _row("USA", "United States", 2024, None)],
]


def fake_fetch(url):
    if "/indicator/" in url:
        return POP_PAGE_2 if url.endswith("page=2") else POP_PAGE_1
    if "/country?" in url:
        return COUNTRIES
    raise AssertionError(f"unexpected URL {url}")


@pytest.fixture
def data():
    return fetch_population(fetch=fake_fetch, today=date(2026, 11, 16))


def test_latest_figure_comes_with_receipt(data):
    latest = data.find("Canada").latest()
    assert latest.value == 40_000_000
    assert latest.year == 2025
    assert latest.indicator == "SP.POP.TOTL"
    assert "World Bank" in latest.citation()
    assert "retrieved 2026-11-16" in latest.citation()
    assert "locations=CAN" in latest.url


def test_reads_every_page(data):
    assert data.find("USA").latest().value == 340_000_000  # from page 2


def test_world_is_kept_other_aggregates_are_excluded(data):
    assert data.find("World").latest().value == 8_000_000_000
    assert data.find("WLD").latest().year == 2025
    assert data.find("Euro area") is None
    assert data.find("EMU") is None


def test_missing_year_is_never_filled_in(data):
    france = data.find("France")
    assert france.get(2025) is None              # null in source stays missing
    assert france.latest().year == 2024          # latest *available* year


def test_specific_year_lookup(data):
    assert data.find("Canada").get(2024).value == 39_000_000
    assert data.find("Canada").get(1900) is None


@pytest.mark.parametrize("name", ["Canada", "canada", "CAN", "ca", "  Canada "])
def test_find_by_name_or_code(data, name):
    assert data.find(name).country.iso3 == "CAN"


@pytest.mark.parametrize("name", ["USA", "US", "United States", "america"])
def test_common_aliases(data, name):
    assert data.find(name).country.iso3 == "USA"


def test_unknown_country_returns_none(data):
    assert data.find("Atlantis") is None


def test_records_world_bank_update_date(data):
    assert data.last_updated == "2026-07-01"


def test_error_response_raises():
    def error_fetch(url):
        return [{"message": [{"id": "120", "key": "Invalid value"}]}]
    with pytest.raises(DataSourceError):
        fetch_population(fetch=error_fetch)


def test_empty_country_list_raises():
    def empty_fetch(url):
        return [{"page": 1, "pages": 1}, []]
    with pytest.raises(DataSourceError):
        fetch_population(fetch=empty_fetch)
