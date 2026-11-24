"""World Bank population data (indicator SP.POP.TOTL), with receipts.

The World Bank API is free and needs no key. Responses are JSON arrays of
[metadata, rows], split into pages. Regional aggregates ("World",
"Euro area") are mixed in with countries, so we filter them out using the
country list, where aggregates have region "Aggregates".

Run once on a computer with internet access to check it works:
    python -m hallucinope.data.worldbank
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date

from .models import Country, DataSourceError, Figure, PopulationData, Series

FILENAME = "worldbank_population.json"  # cache file name
API = "https://api.worldbank.org/v2"
INDICATOR = "SP.POP.TOTL"
INDICATOR_NAME = "Population, total"
SOURCE_NAME = "World Bank, World Development Indicators"
TIMEOUT_SECONDS = 30
PER_PAGE = 20_000

# Fetcher: takes a URL, returns parsed JSON. Injected so tests run offline.
Fetcher = Callable[[str], object]


def http_get_json(url: str) -> object:
    """Default fetcher: HTTP GET with a timeout, parsed as JSON."""
    request = urllib.request.Request(url, headers={"User-Agent": "hallucinope/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DataSourceError(f"[Data:WorldBank] could not reach {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DataSourceError(f"[Data:WorldBank] response was not JSON: {url}") from exc


def _fetch_all_pages(base_url: str, fetch: Fetcher) -> tuple[dict, list[dict]]:
    """Fetch every page of a World Bank endpoint. Returns (first metadata, rows)."""
    rows: list[dict] = []
    page, pages, first_meta = 1, 1, {}
    while page <= pages:
        body = fetch(f"{base_url}&page={page}")
        if not (isinstance(body, list) and len(body) == 2 and isinstance(body[0], dict)):
            # Errors come back as [{"message": [...]}]
            raise DataSourceError(f"[Data:WorldBank] unexpected response: {str(body)[:200]}")
        meta, data = body
        if page == 1:
            first_meta = meta
        pages = int(meta.get("pages", 1))
        rows.extend(data or [])
        page += 1
    return first_meta, rows


WORLD = "WLD"  # the one aggregate kept: AI text often quotes world population


def parse_countries(rows: list[dict]) -> dict[str, Country]:
    """Real countries keyed by ISO3, plus the World; other aggregates removed."""
    countries = {}
    for row in rows:
        if row.get("region", {}).get("value") == "Aggregates" and row.get("id") != WORLD:
            continue
        iso3 = row.get("id", "")
        if len(iso3) == 3:
            countries[iso3] = Country(iso3, row.get("iso2Code", ""), row.get("name", iso3))
    return countries


def parse_population(rows: list[dict], countries: dict[str, Country],
                     retrieved: date) -> dict[str, Series]:
    """Turn indicator rows into one Series per country. Null values are skipped."""
    series = {iso3: Series(c) for iso3, c in countries.items()}
    for row in rows:
        iso3 = row.get("countryiso3code")
        value = row.get("value")
        if iso3 not in series or value is None:
            continue  # an aggregate, or no data for that year: never filled in
        year = int(row["date"])
        series[iso3].figures[year] = make_figure(iso3, year, value, retrieved)
    return series


def make_figure(iso3: str, year: int, value: float, retrieved: date,
                kind: str = "estimate") -> Figure:
    """Build a World Bank population Figure with its full receipt.

    World Bank figures are always estimates; kind is accepted so every
    source shares one signature (the cache relies on that).
    """
    return Figure(
        value=float(value),
        year=year,
        source=SOURCE_NAME,
        indicator=INDICATOR,
        indicator_name=INDICATOR_NAME,
        retrieved=retrieved,
        url=f"https://data.worldbank.org/indicator/{INDICATOR}?locations={iso3}",
        kind=kind,
    )


def fetch_population(fetch: Fetcher | None = None,
                     today: date | None = None) -> PopulationData:
    """Download country list and population figures from the World Bank."""
    fetch = fetch or http_get_json
    _, country_rows = _fetch_all_pages(f"{API}/country?format=json&per_page=400", fetch)
    countries = parse_countries(country_rows)
    if not countries:
        raise DataSourceError("[Data:WorldBank] country list came back empty")
    meta, rows = _fetch_all_pages(
        f"{API}/country/all/indicator/{INDICATOR}?format=json&per_page={PER_PAGE}", fetch)
    series = parse_population(rows, countries, today or date.today())
    return PopulationData(series, last_updated=str(meta.get("lastupdated", "")))


if __name__ == "__main__":
    import sys

    try:
        data = fetch_population()
    except DataSourceError as exc:
        print(f"Download failed. {exc}", file=sys.stderr)
        sys.exit(1)
    with_data = sum(1 for s in data.series.values() if s.figures)
    print(f"Downloaded {with_data} countries (World Bank last updated {data.last_updated})")
    canada = data.find("Canada")
    latest = canada.latest() if canada else None
    if latest:
        print(f"Canada, {latest.year}: {latest.value:,.0f}")
        print(f"Receipt: {latest.citation()}")
