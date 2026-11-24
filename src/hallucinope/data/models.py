"""Source-independent data types shared by every data source.

A Figure is a number plus its receipt. Sources (World Bank now, UN later)
all produce Figures, so the checker never needs to know which one it used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


class DataSourceError(RuntimeError):
    """A data source could not be reached or returned something unexpected."""


@dataclass(frozen=True)
class Figure:
    """One official number, with everything needed to cite it."""

    value: float
    year: int
    source: str          # e.g. "World Bank, World Development Indicators"
    indicator: str       # e.g. "SP.POP.TOTL"
    indicator_name: str  # e.g. "Population, total"
    retrieved: date      # when we downloaded it
    url: str             # where a reader can check it
    kind: str = "estimate"  # "estimate" (measured) or "projection" (forecast)

    def citation(self) -> str:
        year = f"{self.year} {self.kind}" if self.kind != "estimate" else str(self.year)
        return (f"{self.source}, {self.indicator_name} ({self.indicator}), "
                f"{year}; retrieved {self.retrieved.isoformat()}")


@dataclass(frozen=True)
class Country:
    iso3: str            # "CAN"
    iso2: str            # "CA"
    name: str            # "Canada"


@dataclass
class Series:
    """All years of one indicator for one country. Missing years stay missing."""

    country: Country
    figures: dict[int, Figure] = field(default_factory=dict)

    def get(self, year: int) -> Figure | None:
        """The figure for exactly this year, or None. Never interpolated."""
        return self.figures.get(year)

    def latest(self) -> Figure | None:
        """The most recent year that has a value, or None if there is none."""
        return self.figures[max(self.figures)] if self.figures else None


# Common names that differ from official ones, mapped to ISO3 codes. Fuller
# name matching comes in step 6.
ALIASES = {
    "usa": "USA", "us": "USA", "united states of america": "USA", "america": "USA",
    "uk": "GBR", "britain": "GBR", "great britain": "GBR",
    "russia": "RUS", "south korea": "KOR", "north korea": "PRK",
    "egypt": "EGY", "iran": "IRN", "venezuela": "VEN", "syria": "SYR",
    "turkey": "TUR", "vietnam": "VNM", "laos": "LAO", "yemen": "YEM",
    # The World, as AI text usually phrases it
    "global": "WLD", "worldwide": "WLD", "the planet": "WLD", "humanity": "WLD",
    "earth": "WLD", "the globe": "WLD", "mankind": "WLD", "humankind": "WLD",
}


class PopulationData:
    """Population for every country from one source, all available years."""

    def __init__(self, series: dict[str, Series], last_updated: str = ""):
        self.series = series
        self.last_updated = last_updated  # the source's own update date
        self._index: dict[str, str] = {}
        for iso3, s in series.items():
            for key in (iso3, s.country.iso2, s.country.name):
                if key:
                    self._index[key.lower()] = iso3
        for alias, iso3 in ALIASES.items():
            if iso3 in series:
                self._index.setdefault(alias, iso3)

    def find(self, name_or_code: str) -> Series | None:
        """Look up a country by name, ISO2 or ISO3 code. None if not found."""
        iso3 = self._index.get(" ".join(name_or_code.lower().split()))
        return self.series.get(iso3) if iso3 else None
