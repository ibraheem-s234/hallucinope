"""Tests for the UN source, run offline against a fake fetcher.

Responses copy the UN Data Portal's JSON *format* (as seen in a real
response on 2026-11-18); the population values are synthetic.
"""

from datetime import date

import pytest

from hallucinope import config
from hallucinope.data import un
from hallucinope.data.models import DataSourceError

LOCATIONS = {"pageNumber": 1, "pageSize": 1000, "previousPage": None, "nextPage": None,
             "pages": 1, "total": 4, "data": [
                 {"id": 124, "name": "Canada", "iso3": "CAN", "iso2": "CA"},
                 {"id": 250, "name": "France", "iso3": "FRA", "iso2": "FR"},
                 {"id": 158, "name": "Taiwan", "iso3": "TWN", "iso2": "TW"},
                 {"id": 900, "name": "World", "iso3": None, "iso2": None},  # kept
                 {"id": 903, "name": "Africa", "iso3": None, "iso2": None},  # excluded
             ]}


def _row(loc, iso3, name, year, value, sex_id=3, variant_id=4, method="Projection"):
    sex = {1: "Male", 2: "Female", 3: "Both sexes"}[sex_id]
    return {"locationId": loc, "location": name, "iso3": iso3, "locationTypeId": 4,
            "indicatorId": 49, "variantId": variant_id, "variant": "Median",
            "timeLabel": str(year), "estimateMethod": method, "sexId": sex_id,
            "sex": sex, "ageLabel": "Total", "value": value}


ROWS_PAGE_1 = [
    _row(124, "CAN", "Canada", 2024, 19_000_000.5, sex_id=1),   # male: ignored
    _row(124, "CAN", "Canada", 2024, 19_000_000.5, sex_id=2),   # female: ignored
    _row(124, "CAN", "Canada", 2024, 38_000_000),
    _row(124, "CAN", "Canada", 2026, 39_500_000),
    _row(124, "CAN", "Canada", 2026, 37_000_000, variant_id=2),  # Low variant: ignored
]
ROWS_PAGE_2 = [
    _row(250, "FRA", "France", 2025, 67_500_000),
    _row(250, "FRA", "France", 2023, 67_000_000, method="Interpolation"),  # estimate
    _row(158, "TWN", "Taiwan", 2026, 23_000_000),
    # The World is an aggregate (not locationTypeId 4) but is kept; Africa isn't.
    {**_row(900, None, "World", 1950, 2_500_000_000, method="Interpolation"), "locationTypeId": 1},
    {**_row(900, None, "World", 2085, 10_300_000_000), "locationTypeId": 1},
    {**_row(903, None, "Africa", 2026, 1_500_000_000), "locationTypeId": 2},
]


def _page(n, pages, data):
    return {"pageNumber": n, "pages": pages, "nextPage": "more" if n < pages else None,
            "data": data}


def fake_fetch(url):
    if "/locations?" in url:
        return LOCATIONS
    if "/data/indicators/49/" in url:
        return _page(2, 2, ROWS_PAGE_2) if "pageNumber=2" in url else _page(1, 2, ROWS_PAGE_1)
    raise AssertionError(f"unexpected URL {url}")


@pytest.fixture
def data():
    return un.fetch_population(fetch=fake_fetch, today=date(2026, 11, 18))


def test_keeps_both_sexes_median_only(data):
    assert data.find("Canada").get(2024).value == 38_000_000
    assert data.find("Canada").get(2026).value == 39_500_000


def test_projection_label_reaches_the_receipt(data):
    f = data.find("CAN").get(2026)
    assert f.kind == "projection"
    assert "2026 projection" in f.citation()
    assert "World Population Prospects 2024" in f.citation()


def test_non_projection_rows_are_estimates(data):
    assert data.find("France").get(2023).kind == "estimate"


def test_reads_every_page(data):
    assert data.find("Taiwan").get(2026).value == 23_000_000   # page 2


def test_world_is_kept_other_aggregates_are_excluded(data):
    world = data.find("World")
    assert world.get(1950).value == 2_500_000_000 and world.get(1950).kind == "estimate"
    assert world.get(2085).kind == "projection"
    assert data.find("Africa") is None


def test_falls_back_to_one_location_per_request():
    requested = []

    def strict_fetch(url):
        if "/data/" in url:
            ids = url.split("/locations/")[1].split("/")[0]
            requested.append(ids)
            if "," in ids:
                raise un.HTTPStatusError(400, "batching not supported")
            rows = [r for r in ROWS_PAGE_1 + ROWS_PAGE_2 if str(r["locationId"]) == ids]
            return _page(1, 1, rows)
        return fake_fetch(url)

    data = un.fetch_population(fetch=strict_fetch, today=date(2026, 11, 18))
    assert data.find("Canada").get(2026).value == 39_500_000
    assert {"124", "250", "158"} <= set(requested)


def test_rejected_token_is_not_retried_per_location():
    calls = []

    def unauthorized(url):
        calls.append(url)
        if "/data/" in url:
            raise un.HTTPStatusError(401, "[Data:UN] token rejected")
        return fake_fetch(url)

    with pytest.raises(un.HTTPStatusError):
        un.fetch_population(fetch=unauthorized)
    assert len([c for c in calls if "/data/" in c]) == 1


def test_missing_token_gives_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv(config.UN_TOKEN_VAR, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    with pytest.raises(DataSourceError, match="no token configured"):
        un.fetch_population()


def test_unexpected_response_raises():
    with pytest.raises(DataSourceError):
        un.fetch_population(fetch=lambda url: {"error": "nope"})
