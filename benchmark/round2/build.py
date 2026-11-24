"""Round 2: a fresh benchmark with SUBTLE errors. Written 2026-11-24, before any run.

Lessons from round 1:
  * ChatGPT could not plant errors reliably (about 60% of its "planted
    errors" were correct numbers), so here it only wrote accurate paragraphs
    and every error is injected by this script.
  * 30% errors are easy to spot from memory. Real AI mistakes are subtler, so
    numbers are changed by 7% or 12% only.
  * All countries are new (none were in round 1), and the code being graded
    (v1.1, fingerprint 99617723b71b) was frozen before these paragraphs existed.

Targets were chosen by reading the paragraphs: two population figures per
population paragraph (varying the year), and the converted value in two to
four conversions per conversion paragraph, including units Hallucinope may
not support (BTU, miles per gallon) so the test doesn't favour it.

Assumption, reported in the README: ChatGPT's original figures are taken as
correct. A few may be slightly off themselves; disagreements are reviewed.

    python benchmark/round2/build.py    # writes benchmark/round2/benchmark.json
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from build import _find, mutate  # noqa: E402  (same helpers as round 1)

FACTORS = (0.93, 1.07, 0.88, 1.12)     # 7% low, 7% high, 12% low, 12% high

# (batch, id, text as written, occurrence, category)
INJECT = [
    # batch A: Kenya ... Sweden
    ("batchA.json", 1, "57.5 million", 1, "population"),
    ("batchA.json", 1, "16.6 million", 1, "population"),
    ("batchA.json", 2, "70.5 million", 1, "population"),
    ("batchA.json", 2, "34.0 million", 1, "population"),
    ("batchA.json", 3, "6.6 million", 1, "population"),
    ("batchA.json", 3, "32.8 million", 1, "population"),
    ("batchA.json", 4, "38.4 million", 1, "population"),
    ("batchA.json", 4, "28.8 million", 1, "population"),
    ("batchA.json", 5, "34.6 million", 1, "population"),
    ("batchA.json", 5, "21.1 million", 1, "population"),
    ("batchA.json", 6, "25.0 million", 1, "population"),
    ("batchA.json", 6, "46.8 million", 1, "population"),
    ("batchA.json", 7, "36.0 million", 1, "population"),
    ("batchA.json", 7, "13.8 million", 1, "population"),
    ("batchA.json", 8, "29.6 million", 1, "population"),
    ("batchA.json", 8, "38.0 million", 1, "population"),
    ("batchA.json", 9, "18.3 million", 1, "population"),
    ("batchA.json", 9, "14.1 million", 1, "population"),
    ("batchA.json", 10, "7.5 million", 1, "population"),
    ("batchA.json", 10, "10.4 million", 1, "population"),
    # batch B: Chile ... the world
    ("batchB.json", 1, "19.86 million", 1, "population"),
    ("batchB.json", 1, "7.65 million", 1, "population"),
    ("batchB.json", 2, "34.6 million", 1, "population"),
    ("batchB.json", 2, "26.0 million", 1, "population"),
    ("batchB.json", 3, "53.4 million", 1, "population"),
    ("batchB.json", 3, "16.0 million", 1, "population"),
    ("batchB.json", 4, "8.1 million", 1, "population"),
    ("batchB.json", 4, "28.4 million", 1, "population"),
    ("batchB.json", 5, "10.9 million", 1, "population"),
    ("batchB.json", 5, "11.1 million", 1, "population"),
    ("batchB.json", 6, "10.3 million", 1, "population"),
    ("batchB.json", 6, "25.7 million", 1, "population"),
    ("batchB.json", 7, "5.25 million", 1, "population"),
    ("batchB.json", 7, "3.85 million", 1, "population"),
    ("batchB.json", 8, "123.1 million", 1, "population"),
    ("batchB.json", 8, "93.4 million", 1, "population"),
    ("batchB.json", 9, "146.4 million", 1, "population"),
    ("batchB.json", 9, "145.6 million", 1, "population"),
    ("batchB.json", 10, "8.23 billion", 1, "population"),
    ("batchB.json", 10, "3.02 billion", 1, "population"),
    # batch C: conversions
    ("batchC.json", 1, "3.11 miles", 1, "conversion"),
    ("batchC.json", 1, "9.66 minutes per mile", 1, "conversion"),
    ("batchC.json", 1, "1.24 miles", 1, "conversion"),
    ("batchC.json", 1, "16.91 US fluid ounces", 1, "conversion"),
    ("batchC.json", 2, "77°F", 1, "conversion"),
    ("batchC.json", 2, "5.91 inches", 1, "conversion"),
    ("batchC.json", 2, "8.82 ounces", 1, "conversion"),
    ("batchC.json", 3, "15.75 inches", 1, "conversion"),
    ("batchC.json", 3, "1,464.57 cubic inches", 1, "conversion"),
    ("batchC.json", 3, "11.02 pounds", 1, "conversion"),
    ("batchC.json", 4, "10,668 m", 1, "conversion"),
    ("batchC.json", 4, "497.10 miles", 1, "conversion"),
    ("batchC.json", 4, "50.71 pounds", 1, "conversion"),
    ("batchC.json", 5, "6.56 ft", 1, "conversion"),
    ("batchC.json", 5, "32.29 square feet", 1, "conversion"),
    ("batchC.json", 5, "5.30 cubic feet", 1, "conversion"),
    ("batchC.json", 6, "68°F", 1, "conversion"),
    ("batchC.json", 6, "1,765.73 cubic feet", 1, "conversion"),
    ("batchC.json", 7, "29.4 US mpg", 1, "conversion"),
    ("batchC.json", 7, "13.21 US gallon", 1, "conversion"),
    ("batchC.json", 8, "15.53 miles", 1, "conversion"),
    ("batchC.json", 8, "25.36 US fluid ounces", 1, "conversion"),
    ("batchC.json", 8, "10.58 ounces", 1, "conversion"),
    ("batchC.json", 9, "5.51 pounds", 1, "conversion"),
    ("batchC.json", 9, "98.6°F", 1, "conversion"),
    ("batchC.json", 10, "34,121.4 BTU", 1, "conversion"),
    ("batchC.json", 10, "6,824 BTU/h", 1, "conversion"),
]


def load(name):
    return {p["id"]: p["paragraph"] for p in json.loads((HERE / name).read_text("utf-8"))}


def build():
    items = []
    for batch in ("batchA.json", "batchB.json", "batchC.json"):
        for pid, text in load(batch).items():
            items.append({"id": f"{batch[:-5]}#{pid}", "kind": "natural", "text": text,
                          "errors": []})
    for n, (batch, pid, needle, occurrence, category) in enumerate(INJECT):
        original = load(batch)[pid]
        start = _find(original, needle, occurrence)
        factor = FACTORS[n % len(FACTORS)]
        wrong = mutate(needle, factor)
        text = original[:start] + wrong + original[start + len(needle):]
        items.append({"id": f"{batch[:-5]}#{pid}/inject{n + 1}", "kind": "injected",
                      "text": text,
                      "errors": [{"text": wrong, "start": start, "category": category,
                                  "note": f"was {needle!r}, changed x{factor}"}]})
    return items


if __name__ == "__main__":
    items = build()
    (HERE / "benchmark.json").write_text(json.dumps(items, indent=2, ensure_ascii=False),
                                         "utf-8")
    errors = [e for i in items for e in i["errors"]]
    print(f"{len(items)} items ({sum(i['kind'] == 'natural' for i in items)} natural, "
          f"{len(errors)} injected errors: "
          f"{sum(e['category'] == 'population' for e in errors)} population, "
          f"{sum(e['category'] == 'conversion' for e in errors)} conversion)")
