"""Tests for the "estimates first" rule across World Bank and UN data."""

from datetime import date

import pytest

from hallucinope.data import population
from hallucinope.data.models import DataSourceError
import test_un
import test_worldbank

TODAY = date(2026, 11, 18)


def _fail(url):
    raise DataSourceError("[Data:Test] simulated outage")


@pytest.fixture
def pop(tmp_path):
    return population.load(today=TODAY, wb_fetch=test_worldbank.fake_fetch,
                           un_fetch=test_un.fake_fetch,
                           wb_path=tmp_path / "wb.json", un_path=tmp_path / "un.json")


def test_year_covered_by_world_bank_uses_estimate(pop):
    r = pop.lookup("Canada", 2025)
    assert r.figure.value == 40_000_000          # World Bank, not UN
    assert r.figure.kind == "estimate" and "World Bank" in r.figure.source


def test_estimate_wins_even_when_un_has_the_year(pop):
    r = pop.lookup("Canada", 2024)               # both sources have 2024
    assert r.figure.value == 39_000_000          # World Bank's 2024, not UN's 38M


def test_future_year_uses_un_projection_and_says_so(pop):
    r = pop.lookup("Canada", 2026)
    assert r.figure.value == 39_500_000
    assert r.figure.kind == "projection"
    assert "UN projection" in r.note


def test_no_year_uses_latest_estimate(pop):
    r = pop.lookup("Canada")
    assert r.figure.year == 2025 and r.figure.kind == "estimate"


def test_world_bank_gap_is_filled_by_un_with_label(pop):
    r = pop.lookup("France", 2025)               # World Bank has no 2025 for France
    assert r.figure.value == 67_500_000
    assert "no World Bank estimate for 2025" in r.note


def test_country_only_in_un(pop):
    r = pop.lookup("Taiwan", 2026)
    assert r.figure.value == 23_000_000


def test_no_figure_means_cant_verify(pop):
    r = pop.lookup("Canada", 1900)
    assert r.figure is None and r.country.name == "Canada"


def test_unknown_country(pop):
    r = pop.lookup("Atlantis", 2025)
    assert r.figure is None and r.country is None


def test_un_unavailable_falls_back_to_world_bank(tmp_path):
    pop = population.load(today=TODAY, wb_fetch=test_worldbank.fake_fetch, un_fetch=_fail,
                          wb_path=tmp_path / "wb.json", un_path=tmp_path / "un.json")
    assert pop.lookup("Canada", 2025).figure.value == 40_000_000
    assert pop.lookup("Canada", 2026).figure is None     # no guessing without the UN
    assert any("UN unavailable" in n for n in pop.notes)


def test_both_sources_down_raises(tmp_path):
    with pytest.raises(DataSourceError):
        population.load(today=TODAY, wb_fetch=_fail, un_fetch=_fail,
                        wb_path=tmp_path / "wb.json", un_path=tmp_path / "un.json")


def test_projection_label_survives_the_cache(tmp_path):
    kwargs = dict(wb_path=tmp_path / "wb.json", un_path=tmp_path / "un.json")
    population.load(today=TODAY, wb_fetch=test_worldbank.fake_fetch,
                    un_fetch=test_un.fake_fetch, **kwargs)
    reloaded = population.load(today=TODAY, wb_fetch=_fail, un_fetch=_fail, **kwargs)
    f = reloaded.lookup("Canada", 2026).figure
    assert f.kind == "projection" and "2026 projection" in f.citation()
