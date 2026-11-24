"""Local cache for population data, so Hallucinope works offline.

load_population() is the one entry point the rest of the project uses:
  * fresh cache (under max_age_days old)  -> use it, no network
  * stale or missing cache                -> download, save, use it
  * download fails but a stale cache exists -> use the stale copy and say so
  * download fails and there is no cache  -> DataSourceError

Each figure keeps the date it was originally downloaded, so a receipt never
claims data is newer than it is. Writes are atomic: a crash mid-save can
never leave a half-written, corrupted cache file behind.

    python -m hallucinope.data.cache            # load (download if needed)
    python -m hallucinope.data.cache --refresh  # force a fresh download
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import ModuleType

from .. import config
from . import worldbank
from .models import Country, DataSourceError, PopulationData, Series
from .worldbank import Fetcher

log = logging.getLogger("hallucinope.data.cache")

# A "source" is a module (worldbank, un) providing FILENAME, SOURCE_NAME,
# INDICATOR, make_figure() and fetch_population(fetch=, today=).
SCHEMA_VERSION = 2  # 2: adds World figures and UN 1950-2100; older caches re-download
FILENAME = worldbank.FILENAME
DEFAULT_MAX_AGE_DAYS = 30


@dataclass
class LoadResult:
    data: PopulationData
    retrieved: date      # when this data was downloaded
    from_cache: bool     # True if no download happened
    stale: bool          # True if we fell back to old data after a failed download
    path: Path


def save(data: PopulationData, retrieved: date, path: Path,
         source: ModuleType = worldbank) -> None:
    """Write the dataset to path atomically (temp file, then rename)."""
    payload = {
        "schema": SCHEMA_VERSION,
        "source": source.SOURCE_NAME,
        "indicator": source.INDICATOR,
        "last_updated": data.last_updated,
        "retrieved": retrieved.isoformat(),
        "countries": {
            iso3: {
                "iso2": s.country.iso2,
                "name": s.country.name,
                "values": {str(y): f.value for y, f in sorted(s.figures.items())},
                "projections": sorted(y for y, f in s.figures.items()
                                      if f.kind == "projection"),
            }
            for iso3, s in data.series.items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)  # atomic on Windows, macOS and Linux
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load(path: Path, source: ModuleType = worldbank) -> tuple[PopulationData, date] | None:
    """Read a cache file. Returns None if missing, corrupt, or an old schema."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != SCHEMA_VERSION:
            return None
        if payload.get("source", source.SOURCE_NAME) != source.SOURCE_NAME:
            return None  # someone else's file: never mix sources
        retrieved = date.fromisoformat(payload["retrieved"])
        series = {}
        for iso3, c in payload["countries"].items():
            s = Series(Country(iso3, c["iso2"], c["name"]))
            projections = set(c.get("projections", []))  # absent in older files
            for year, value in c["values"].items():
                kind = "projection" if int(year) in projections else "estimate"
                s.figures[int(year)] = source.make_figure(iso3, int(year), value,
                                                          retrieved, kind)
            series[iso3] = s
        return PopulationData(series, last_updated=payload.get("last_updated", "")), retrieved
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        log.warning("[Data:Cache] ignoring unreadable cache %s: %s", path, exc)
        return None


def load_population(
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    refresh: bool = False,
    path: Path | None = None,
    fetch: Fetcher | None = None,
    today: date | None = None,
    source: ModuleType = worldbank,
) -> LoadResult:
    """Population data from the cache if fresh enough, otherwise downloaded."""
    path = path or config.cache_dir() / source.FILENAME
    today = today or date.today()
    cached = load(path, source)

    if cached and not refresh and (today - cached[1]).days <= max_age_days:
        return LoadResult(cached[0], cached[1], from_cache=True, stale=False, path=path)

    try:
        data = source.fetch_population(fetch=fetch, today=today)
    except DataSourceError as exc:
        if cached:
            log.warning("[Data:Cache] download failed, using data from %s: %s",
                        cached[1].isoformat(), exc)
            return LoadResult(cached[0], cached[1], from_cache=True, stale=True, path=path)
        raise
    save(data, today, path, source)
    return LoadResult(data, today, from_cache=False, stale=False, path=path)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        result = load_population(refresh="--refresh" in sys.argv)
    except DataSourceError as exc:
        print(f"No data available. {exc}", file=sys.stderr)
        sys.exit(1)
    how = "loaded from cache" if result.from_cache else "downloaded and saved"
    print(f"Population data {how}: {result.path}")
    print(f"Downloaded on {result.retrieved.isoformat()}"
          + (" (STALE: latest download failed)" if result.stale else ""))
    canada = result.data.find("Canada")
    latest = canada.latest() if canada else None
    if latest:
        print(f"Canada, {latest.year}: {latest.value:,.0f}  [{latest.citation()}]")
