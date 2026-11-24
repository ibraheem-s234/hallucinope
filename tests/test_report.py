"""End-to-end tests: paragraph in, verdicts out.

Canada's figures are real (2026-11-16/18 downloads); France's is synthetic.
"""

from datetime import date

import pytest

from hallucinope import config
from hallucinope.__main__ import render
from hallucinope.checks.population_claims import Verdict
from hallucinope.data import un, worldbank
from hallucinope.data.models import Country, PopulationData, Series
from hallucinope.data.population import Population
from hallucinope.report import check_text

DAY = date(2026, 11, 18)
CANADA, FRANCE = Country("CAN", "CA", "Canada"), Country("FRA", "FR", "France")

TEXT = ("Canada has about 38 million people, while France is home to roughly 68 million. "
        "By 2026 Canada will pass 40 million. The drive from Toronto to Kingston is 260 km "
        "(about 100 miles), and it was 20 °C (68 °F). Prices rose 12% and 5 million "
        "tourists visited.")


def _series(country, figures):
    s = Series(country)
    for f in figures:
        s.figures[f.year] = f
    return s


@pytest.fixture
def population():
    wb = PopulationData({
        "CAN": _series(CANADA, [worldbank.make_figure("CAN", 2025, 41_651_653, DAY)]),
        "FRA": _series(FRANCE, [worldbank.make_figure("FRA", 2025, 68_600_000, DAY)]),
    })
    unp = PopulationData({
        "CAN": _series(CANADA, [un.make_figure("CAN", 2026, 40_467_728, DAY, "projection")]),
    })
    return Population(wb, unp, notes=["UN: using data from 2026-11-18"])


@pytest.fixture
def report(population):
    return check_text(TEXT, population)


def test_every_claim_gets_the_right_verdict(report):
    assert [(c.claim.text.split(" (")[0], c.verdict) for c in report.checked] == [
        ("38 million", Verdict.WRONG),
        ("68 million", Verdict.CORRECT),
        ("40 million", Verdict.CORRECT),     # over 40M: consistent with UN 2026 projection
        ("260 km", Verdict.WRONG),           # 260 km is 161.6 miles
        ("20 °C", Verdict.CORRECT),
    ]


def test_positions_point_at_the_claims(report):
    for c in report.checked:
        assert TEXT[c.start:c.end] == c.claim.text


def test_population_verdicts_carry_their_receipt(report):
    wrong = report.checked[0]
    assert wrong.figure.value == 41_651_653 and "World Bank" in wrong.figure.citation()
    assert "not 38 million" in wrong.message


def test_conversion_message(report):
    assert report.checked[3].message.startswith("Wrong: 260 km = 161.6 miles, not 100 miles")


def test_unchecked_numbers_and_notes(report):
    assert [s.text for s in report.unchecked] == ["12%", "5 million"]
    assert report.notes == ["UN: using data from 2026-11-18"]


def test_counts(report):
    assert (report.count(Verdict.CORRECT), report.count(Verdict.WRONG)) == (3, 2)


def test_render_marks_claims_and_summarises(report):
    out = render(report, color=False)
    assert "about 38 million[1] people" in out
    assert "[1] WRONG  Canada's population is 41,651,653" in out
    assert "source: World Bank" in out
    assert "Summary: 3 correct, 2 wrong." in out
    assert "2 other numbers not checked: 12%, 5 million" in out
    assert "\033[" not in out                      # no color codes when color is off


def test_render_with_no_claims(population):
    out = render(check_text("Nothing numeric here.", population))
    assert "No checkable claims found." in out


@pytest.mark.parametrize("value, expected", [(None, False), ("1", True), ("true", True),
                                             ("0", False), ("off", False)])
def test_ai_is_off_unless_switched_on(monkeypatch, tmp_path, value, expected):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HALLUCINOPE_USE_LLM", raising=False)
    if value is not None:
        monkeypatch.setenv("HALLUCINOPE_USE_LLM", value)
    assert config.use_llm() is expected
