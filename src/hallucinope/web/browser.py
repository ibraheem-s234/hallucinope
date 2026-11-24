"""Entry point for the website version, where Python runs inside the browser (Pyodide).

The page writes the bundled data snapshot into Pyodide's file system, then calls:

    init("/data/worldbank_population.json", "/data/un_population.json")  -> JSON text
    check("Canada has 41.7 million people.")                             -> JSON text

Nothing here touches the network: the data is a snapshot made by build_site.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..data import cache, un, worldbank
from ..data.population import Population
from .payload import MAX_TEXT, Checker

_checker: Checker | None = None


def init(wb_path: str, un_path: str) -> str:
    """Load the snapshot. Returns JSON: {"ok", "worldbank", "un", "notes"} (dates as text)."""
    global _checker
    notes: list[str] = []
    wb = cache.load(Path(wb_path), worldbank)
    un_data = cache.load(Path(un_path), un)
    if wb is None:
        notes.append("World Bank data snapshot missing")
    if un_data is None:
        notes.append("UN projections not included in this snapshot")
    if wb is None and un_data is None:
        _checker = None
        return json.dumps({"ok": False, "notes": notes})
    population = Population(wb[0] if wb else None, un_data[0] if un_data else None, notes)
    _checker = Checker(population)
    return json.dumps({
        "ok": True,
        "worldbank": wb[1].isoformat() if wb else None,
        "un": un_data[1].isoformat() if un_data else None,
        "notes": notes,
    })


def check(text: str) -> str:
    """Check a paragraph. Returns the same JSON the local server's /api/check returns."""
    if _checker is None:
        return json.dumps({"error": "The data hasn't loaded yet. Refresh the page."})
    text = (text or "").strip()
    if not text:
        return json.dumps({"error": "Paste some text to check."})
    if len(text) > MAX_TEXT:
        return json.dumps({"error": f"That's {len(text):,} characters. "
                                    f"Check up to {MAX_TEXT:,} at a time."})
    return json.dumps(_checker.check(text))