"""Builds the website version of Hallucinope into docs/, for GitHub Pages.

    python -m hallucinope.web.build_site             # writes docs/
    python -m hallucinope.web.build_site --out site  # somewhere else

The website runs the real Python checker in the visitor's browser (Pyodide),
with a snapshot of the population data. What goes into docs/:

    index.html                 the page, told to use Python in the browser
    static/                    style.css, app.js, samples.js, hallucinope.zip (the code)
    data/                      the World Bank and UN data snapshot
    .nojekyll                  tells GitHub Pages to serve the files as they are

No token or .env file is ever copied: only *.py files go into the zip, and the
data files are the cached downloads, which contain figures only.
Other files already in docs/ (like screenshot.png) are left alone.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

from .. import config
from ..data import un, worldbank
from ..data.models import DataSourceError
from ..data.population import load

PACKAGE = Path(__file__).resolve().parents[1]          # src/hallucinope
STATIC = Path(__file__).with_name("static")
PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
SCRIPT_TAG = '  <script src="static/samples.js"></script>'


def page_html(source: str) -> str:
    """The local page, plus one line that switches it to Python-in-the-browser."""
    if source.count(SCRIPT_TAG) != 1:
        raise ValueError("index.html changed: can't find where to add the website setting")
    setting = json.dumps({"pyodide": PYODIDE})
    return source.replace(SCRIPT_TAG,
                          f"  <script>window.HALLUCINOPE_STATIC = {setting};</script>\n"
                          + SCRIPT_TAG)


def zip_code(dest: Path) -> list[str]:
    """Zip every .py file of the package (nothing else). Returns the names inside."""
    names = []
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(PACKAGE.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            name = "hallucinope/" + path.relative_to(PACKAGE).as_posix()
            z.write(path, name)
            names.append(name)
    return names


def build(out: Path, data_dir: Path) -> list[str]:
    """Write the site to out/, taking data files from data_dir. Returns notes."""
    notes = []
    (out / "static").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(exist_ok=True)
    (out / "index.html").write_text(
        page_html((STATIC / "index.html").read_text(encoding="utf-8")), encoding="utf-8")
    for name in ("style.css", "app.js", "samples.js"):
        shutil.copyfile(STATIC / name, out / "static" / name)
    zip_code(out / "static" / "hallucinope.zip")

    for source in (worldbank, un):
        cached = data_dir / source.FILENAME
        if cached.is_file():
            shutil.copyfile(cached, out / "data" / source.FILENAME)
        else:
            (out / "data" / source.FILENAME).unlink(missing_ok=True)   # never ship old data
            notes.append(f"{source.SOURCE_NAME}: no data downloaded, left out of the site")
    if not (out / "data" / worldbank.FILENAME).is_file() \
            and not (out / "data" / un.FILENAME).is_file():
        raise DataSourceError("no population data to put in the site")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hallucinope.web.build_site",
                                     description="Build the website into docs/.")
    parser.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args(argv)

    print("Making sure the population data is up to date...")
    try:
        population = load()       # downloads only if the cache is over 30 days old
    except DataSourceError as exc:
        print(f"No population data available. {exc}", file=sys.stderr)
        return 1
    for note in population.notes:
        print(f"Note: {note}")
    try:
        notes = build(args.out, config.cache_dir())
    except (OSError, ValueError, DataSourceError) as exc:
        print(f"Couldn't build the site: {exc}", file=sys.stderr)
        return 1
    for note in notes:
        print(f"Note: {note}")
    print(f"Website built in {args.out.resolve()}")
    print(f"Try it: cd {args.out}  then  python -m http.server 8001  "
          "and open http://localhost:8001")
    return 0


if __name__ == "__main__":
    sys.exit(main())