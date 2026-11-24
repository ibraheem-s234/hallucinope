"""UN World Population Prospects 2024: total population incl. projections.

Requires a free bearer token (valid one year), read from .env via config.
Indicator 49 returns three rows per country-year (male, female, both
sexes); we keep "Both sexes" and the Median variant. Each row says whether
it is a measured estimate or a projection, and that label travels with the
figure into its receipt. In WPP 2024, every year from 2024 is a projection.

    python -m hallucinope.data.un      # download once and print Canada
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import date

from .. import config
from .models import Country, DataSourceError, Figure, PopulationData, Series
from .worldbank import Fetcher

log = logging.getLogger("hallucinope.data.un")

FILENAME = "un_population.json"  # cache file name
HOST = "https://population.un.org"
API = f"{HOST}/dataportalapi/api/v1"
INDICATOR_ID = 49
SOURCE_NAME = "United Nations, World Population Prospects 2024"
INDICATOR = "WPP indicator 49"
INDICATOR_NAME = "Total population, both sexes (median variant)"
SOURCE_URL = f"{HOST}/wpp/"
# The full WPP range: 1950 estimates (before World Bank data starts in 1960)
# through 2100 projections ("10.3 billion by the mid-2080s").
START_YEAR, END_YEAR = 1950, 2100
BATCH_SIZE = 40          # locations per request
PAGE_SIZE = 1000
TIMEOUT_SECONDS = 30
BOTH_SEXES, MEDIAN, COUNTRY_TYPE = 3, 4, 4
WORLD_ID = 900           # UN M49 code for the World (an aggregate, no ISO3)
WORLD = Country("WLD", "", "World")


class HTTPStatusError(DataSourceError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def make_fetcher(token: str) -> Fetcher:
    """An authenticated fetcher. The token is used in a header, never logged."""
    def fetch(url: str) -> object:
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}", "User-Agent": "hallucinope/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise HTTPStatusError(exc.code, "[Data:UN] token rejected (it may have "
                                      "expired; tokens last one year)") from exc
            raise HTTPStatusError(exc.code, f"[Data:UN] HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DataSourceError(f"[Data:UN] could not reach {url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DataSourceError(f"[Data:UN] response was not JSON: {url}") from exc
    return fetch


def _fetch_all_pages(url: str, fetch: Fetcher) -> list[dict]:
    """Follow the UN's paging ({pageNumber, pages, nextPage, data}) to the end."""
    rows: list[dict] = []
    page = 1
    while True:
        body = fetch(url if page == 1 else f"{url}&pageNumber={page}")
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise DataSourceError(f"[Data:UN] unexpected response: {str(body)[:200]}")
        rows.extend(body["data"])
        if not body.get("nextPage") or page >= int(body.get("pages") or 1):
            return rows
        page += 1


def parse_locations(rows: list[dict]) -> dict[int, Country]:
    """UN location id -> Country: entries with an ISO3 code, plus the World."""
    locations = {int(r["id"]): Country(r["iso3"], r.get("iso2") or "", r.get("name", r["iso3"]))
                 for r in rows if isinstance(r.get("iso3"), str) and len(r["iso3"]) == 3}
    locations[WORLD_ID] = WORLD
    return locations


def parse_rows(rows: list[dict], locations: dict[int, Country],
               retrieved: date) -> dict[str, Series]:
    """Keep 'Both sexes', Median variant, country-level rows only."""
    series: dict[str, Series] = {}
    for r in rows:
        if r.get("sexId") != BOTH_SEXES or r.get("variantId") != MEDIAN:
            continue
        is_world = int(r.get("locationId", 0)) == WORLD_ID
        if r.get("value") is None or (
                not is_world and r.get("locationTypeId", COUNTRY_TYPE) != COUNTRY_TYPE):
            continue
        country = locations.get(int(r["locationId"]))
        if country is None:
            continue
        kind = "projection" if r.get("estimateMethod") == "Projection" else "estimate"
        year = int(r["timeLabel"])
        s = series.setdefault(country.iso3, Series(country))
        s.figures[year] = make_figure(country.iso3, year, r["value"], retrieved, kind)
    return series


def make_figure(iso3: str, year: int, value: float, retrieved: date,
                kind: str = "projection") -> Figure:
    return Figure(value=float(value), year=year, source=SOURCE_NAME, indicator=INDICATOR,
                  indicator_name=INDICATOR_NAME, retrieved=retrieved, url=SOURCE_URL,
                  kind=kind)


def _data_url(location_ids: list[int]) -> str:
    ids = ",".join(str(i) for i in location_ids)
    return (f"{API}/data/indicators/{INDICATOR_ID}/locations/{ids}/start/{START_YEAR}"
            f"/end/{END_YEAR}?pagingInHeader=false&format=json&pageSize={PAGE_SIZE}")


def _fetch_rows(ids: list[int], fetch: Fetcher) -> list[dict]:
    """Fetch a batch of locations; if the API rejects batching, go one by one."""
    try:
        return _fetch_all_pages(_data_url(ids), fetch)
    except HTTPStatusError as exc:
        if exc.status in (401, 403):
            raise
        if len(ids) == 1:
            log.warning("[Data:UN] no data for location %s: %s", ids[0], exc)
            return []
        rows: list[dict] = []
        for i in ids:
            rows.extend(_fetch_rows([i], fetch))
        return rows


def fetch_population(fetch: Fetcher | None = None,
                     today: date | None = None) -> PopulationData:
    """Download total population for every country from the UN Data Portal."""
    if fetch is None:
        token = config.un_token()
        if not token:
            raise DataSourceError(f"[Data:UN] no token configured; add "
                                  f"{config.UN_TOKEN_VAR}=... to your .env file")
        fetch = make_fetcher(token)
    locations = parse_locations(
        _fetch_all_pages(f"{API}/locations?format=json&pageSize={PAGE_SIZE}", fetch))
    if not locations:
        raise DataSourceError("[Data:UN] location list came back empty")
    ids = sorted(locations)
    rows: list[dict] = []
    for start in range(0, len(ids), BATCH_SIZE):
        rows.extend(_fetch_rows(ids[start:start + BATCH_SIZE], fetch))
    series = parse_rows(rows, locations, today or date.today())
    if not series:
        raise DataSourceError("[Data:UN] no population rows were returned")
    return PopulationData(series, last_updated="WPP 2024")


if __name__ == "__main__":
    import sys

    try:
        data = fetch_population()
    except DataSourceError as exc:
        print(f"Download failed. {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Downloaded {len(data.series)} countries from the UN")
    canada = data.find("Canada")
    for year in (2024, 2026):
        f = canada.get(year) if canada else None
        if f:
            print(f"Canada, {year}: {f.value:,.0f}  [{f.citation()}]")
