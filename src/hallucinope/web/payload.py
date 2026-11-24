"""Turns a checked paragraph into the JSON the page draws from.

Shared by the local server (server.py) and the in-browser version
(browser.py), so both give exactly the same results.
"""

from __future__ import annotations

import threading

from ..checks.population_claims import Verdict
from ..data.models import Figure
from ..data.population import Population
from ..extract.countries import CountryIndex
from ..report import CheckedClaim, Report, check_text
from ..units.convert import check_conversion

MAX_TEXT = 5_000                 # characters per check

VERDICT_KEYS = {Verdict.CORRECT: "correct", Verdict.WRONG: "wrong",
                Verdict.UNCONFIRMED: "unconfirmed", Verdict.CANT_VERIFY: "cant_verify"}


def _figure(f: Figure | None) -> dict | None:
    if f is None:
        return None
    return {"value": f.value, "year": f.year, "kind": f.kind, "url": f.url,
            "source": f.source, "citation": f.citation()}


def _claim(i: int, c: CheckedClaim) -> dict:
    detail = c.message.split(": ", 1)[1] if ": " in c.message else c.message
    out = {
        "id": i, "start": c.start, "end": c.end, "text": c.claim.text,
        "kind": c.claim.kind, "verdict": VERDICT_KEYS[c.verdict], "detail": detail,
        "figure": _figure(c.figure), "latest": _figure(c.latest_estimate),
    }
    if c.claim.kind == "conversion":
        conv = c.claim.conversion
        try:
            expected = check_conversion(conv.value, conv.unit, conv.stated_value,
                                        conv.stated_unit).expected
        except ValueError:
            expected = None
        out["conversion"] = {"value": conv.value, "unit": conv.unit,
                             "stated": conv.stated_value, "stated_unit": conv.stated_unit,
                             "expected": expected}
    return out


def build_payload(report: Report) -> dict:
    """Everything the page needs to mark the text and write the cards."""
    claims = [_claim(i, c) for i, c in enumerate(report.checked, 1)]
    for claim in claims:   # "20 °C (68 °F" -> include the closing bracket in the mark
        if "(" in claim["text"] and ")" not in claim["text"] \
                and report.text[claim["end"]:claim["end"] + 1] == ")":
            claim["end"] += 1
            claim["text"] += ")"
    return {
        "text": report.text,
        "claims": claims,
        "unchecked": [{"start": s.start, "end": s.end, "text": s.text, "kind": s.kind}
                      for s in report.unchecked],
        "counts": {key: report.count(v) for v, key in VERDICT_KEYS.items()},
        "notes": report.notes,
    }


class Checker:
    """Holds the data, loaded once, and answers check requests."""

    def __init__(self, population: Population):
        self.population = population
        self.countries = CountryIndex.from_population(population)
        self._lock = threading.Lock()   # the extractor is cheap; keep it simple and safe

    def check(self, text: str) -> dict:
        with self._lock:
            return build_payload(check_text(text, self.population, self.countries))