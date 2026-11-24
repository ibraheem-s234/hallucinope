"""Population lookup across sources, using the "estimates first" rule.

  * A year the World Bank covers  -> World Bank estimate (measured data)
  * A year it doesn't (e.g. 2026) -> UN figure, labelled as a projection
  * No year given                 -> the latest World Bank estimate

Why: a projection made years ago can be far off. WPP 2024 put Canada at
39.7M for 2024, before an immigration surge; the World Bank's 2025
estimate is 41.7M. Trusting the newest figure would mark correct claims
wrong. If the UN is unavailable (no token, offline), the World Bank alone
is used and a note says so.

    python -m hallucinope.data.population            # load both sources
    python -m hallucinope.data.population --refresh  # force fresh downloads
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import cache, un, worldbank
from .models import Country, DataSourceError, Figure, PopulationData
from .worldbank import Fetcher


@dataclass(frozen=True)
class Lookup:
    figure: Figure | None    # None means "can't verify" — never a guess
    country: Country | None
    note: str


@dataclass
class Population:
    worldbank: PopulationData | None
    un: PopulationData | None
    notes: list[str] = field(default_factory=list)   # e.g. "UN unavailable: ..."

    def lookup(self, country: str, year: int | None = None) -> Lookup:
        wb = self.worldbank.find(country) if self.worldbank else None
        un_s = self.un.find(country) if self.un else None
        found = (wb or un_s).country if (wb or un_s) else None
        if found is None:
            return Lookup(None, None, f"unknown country: {country!r}")

        if year is None:
            if wb and wb.latest():
                return Lookup(wb.latest(), found, "latest estimate")
            year = date.today().year  # no World Bank data: use the UN for this year

        if wb and wb.get(year):
            return Lookup(wb.get(year), found, "estimate")
        if un_s and un_s.get(year):
            f = un_s.get(year)
            return Lookup(f, found, f"no World Bank estimate for {year}; UN {f.kind} used")
        return Lookup(None, found, f"no figure for {found.name} in {year}")


def load(refresh: bool = False, max_age_days: int = cache.DEFAULT_MAX_AGE_DAYS,
         today: date | None = None,
         wb_fetch: Fetcher | None = None, un_fetch: Fetcher | None = None,
         wb_path: Path | None = None, un_path: Path | None = None) -> Population:
    """Load both sources from cache or network. Fails only if both fail."""
    notes: list[str] = []
    datasets: dict[str, PopulationData | None] = {}
    for name, source, fetch, path in (("World Bank", worldbank, wb_fetch, wb_path),
                                      ("UN", un, un_fetch, un_path)):
        try:
            result = cache.load_population(max_age_days=max_age_days, refresh=refresh,
                                           path=path, fetch=fetch, today=today,
                                           source=source)
            datasets[name] = result.data
            if result.stale:
                notes.append(f"{name}: using data from {result.retrieved} "
                             "(latest download failed)")
        except DataSourceError as exc:
            datasets[name] = None
            notes.append(f"{name} unavailable: {exc}")
    if not datasets["World Bank"] and not datasets["UN"]:
        raise DataSourceError("no population source available: " + "; ".join(notes))
    return Population(datasets["World Bank"], datasets["UN"], notes)


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        pop = load(refresh="--refresh" in sys.argv)
    except DataSourceError as exc:
        print(f"No data available. {exc}", file=sys.stderr)
        sys.exit(1)
    for note in pop.notes:
        print(f"Note: {note}")
    for year in (2025, 2026, None):
        r = pop.lookup("Canada", year)
        label = year or "no year"
        if r.figure:
            print(f"Canada ({label}): {r.figure.value:,.0f} — {r.note}\n"
                  f"    receipt: {r.figure.citation()}")
        else:
            print(f"Canada ({label}): can't verify — {r.note}")
