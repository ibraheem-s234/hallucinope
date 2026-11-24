"""Tests for the local cache. Uses pytest's tmp_path, never the real cache."""

from datetime import date

import pytest

from hallucinope import config
from hallucinope.data.cache import load_population
from hallucinope.data.models import DataSourceError
from test_worldbank import fake_fetch

DAY_1 = date(2026, 11, 16)


class CountingFetch:
    """Wraps the fake fetcher and counts calls, to prove when we hit the network."""

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def __call__(self, url):
        self.calls += 1
        if self.fail:
            raise DataSourceError("[Data:WorldBank] simulated outage")
        return fake_fetch(url)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "cache" / "population.json"


def test_first_load_downloads_and_saves(path):
    fetch = CountingFetch()
    result = load_population(path=path, fetch=fetch, today=DAY_1)
    assert fetch.calls > 0 and path.exists()
    assert not result.from_cache


def test_second_load_uses_cache_without_network(path):
    load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    fetch = CountingFetch()
    result = load_population(path=path, fetch=fetch, today=date(2026, 11, 20))
    assert fetch.calls == 0
    assert result.from_cache and not result.stale


def test_round_trip_keeps_values_and_original_receipt_date(path):
    load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    result = load_population(path=path, fetch=CountingFetch(), today=date(2026, 12, 1))
    canada = result.data.find("Canada")
    assert canada.latest().value == 40_000_000
    assert canada.latest().retrieved == DAY_1          # not the day it was reloaded
    assert "retrieved 2026-11-16" in canada.latest().citation()
    assert result.data.last_updated == "2026-07-01"


def test_missing_year_stays_missing_after_round_trip(path):
    load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    result = load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    assert result.data.find("France").get(2025) is None


def test_old_cache_is_refreshed(path):
    load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    fetch = CountingFetch()
    result = load_population(path=path, fetch=fetch, today=date(2026, 12, 31))  # 45 days
    assert fetch.calls > 0 and not result.from_cache
    assert result.retrieved == date(2026, 12, 31)


def test_refresh_forces_download(path):
    load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    fetch = CountingFetch()
    load_population(path=path, fetch=fetch, today=DAY_1, refresh=True)
    assert fetch.calls > 0


def test_offline_falls_back_to_stale_cache(path):
    load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    result = load_population(path=path, fetch=CountingFetch(fail=True), today=date(2027, 3, 1))
    assert result.stale
    assert result.data.find("Canada").latest().retrieved == DAY_1


def test_offline_with_no_cache_raises(path):
    with pytest.raises(DataSourceError):
        load_population(path=path, fetch=CountingFetch(fail=True), today=DAY_1)


@pytest.mark.parametrize("contents", ["{not json", '{"schema": 999}', '{"schema": 1}', ""])
def test_corrupt_or_outdated_cache_is_replaced(path, contents):
    path.parent.mkdir(parents=True)
    path.write_text(contents, encoding="utf-8")
    fetch = CountingFetch()
    result = load_population(path=path, fetch=fetch, today=DAY_1)
    assert fetch.calls > 0
    assert result.data.find("Canada").latest().value == 40_000_000


def test_no_temp_files_left_behind(path):
    load_population(path=path, fetch=CountingFetch(), today=DAY_1)
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_cache_dir_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("HALLUCINOPE_CACHE_DIR", str(tmp_path / "custom"))
    assert config.cache_dir() == tmp_path / "custom"
