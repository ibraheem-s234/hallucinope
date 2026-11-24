"""Build benchmark.json from the ChatGPT batches. Written 2026-11-24, BEFORE any run.

Three kinds of benchmark item:

  natural      the 20 paragraphs written without deliberate errors (batches 4-5).
               Measures FALSE ALARMS: every number is assumed correct; any red
               verdict is reviewed afterwards (ChatGPT may have erred for real).
  chatgpt      ChatGPT's planted errors that were checked by hand and found to
               be genuine (decisions below). About 60% of its "planted errors"
               were correct numbers, so its keys could not be used as-is.
  injected     a copy of a natural paragraph with ONE number changed by 30% by
               this script, so it is wrong by construction. Measures CATCH RATE
               without trusting any answer key.

Targets for injection were chosen by reading the paragraphs (country/world
population figures for measured years, and the result side of unit
conversions), not by running Hallucinope, so the choice can't favour it.

    python benchmark/build.py        # writes benchmark/benchmark.json
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
FACTORS = (0.7, 1.3)          # alternate: 30% too low, 30% too high


def load(name):
    return {p["id"]: p["paragraph"] for p in json.loads((HERE / name).read_text("utf-8"))}


# --- ChatGPT's planted errors, adjudicated by hand ---------------------------
# (batch, id, text as written, category, decision note)
CHATGPT_REAL = [
    ("batch1.json", 1, "280 million", "population", "Nigeria 2025: ~238M (17% off)"),
    ("batch1.json", 2, "110 million", "population", "Ethiopia 2025: ~135M (19% off)"),
    ("batch1.json", 4, "75 million", "population", "Bangladesh 1971: ~67M (12% off)"),
    ("batch2.json", 1, "24.5 million", "population", "Canada 1960: 17.9M (37% off)"),
    ("batch3.json", 1, "300 mL", "conversion", "1 US cup = 236.6 mL"),
    ("batch3.json", 2, "4.0 miles", "conversion", "5 km = 3.11 miles"),
    ("batch3.json", 3, "80°F", "conversion", "20 °C = 68 °F"),
    ("batch3.json", 4, "120 km/h", "conversion", "60 mph = 96.6 km/h"),
    ("batch3.json", 5, "190 lb", "conversion", "70 kg = 154.3 lb"),
    ("batch3.json", 6, "15 m²", "conversion", "120 sq ft = 11.15 m²"),
    ("batch3.json", 8, "1.5 US cups", "conversion", "250 mL = 1.06 US cups"),
    ("batch3.json", 9, "25°C", "conversion", "68 °F = 20 °C"),
    ("batch3.json", 10, "100 kg", "conversion", "180 lb = 81.6 kg"),
]
# Rejected, for the record: batch1 #5 Vietnam 30M (1960) and #7 Iran 22M (1960)
# are within normal rounding; #6 Manila and #9 Bangkok are cities; #8 Turkey
# 28 vs 28.2M is rounding; #10 "566 million" is a sum (arithmetic, out of
# scope). batch2 #2-#10 list correct values as errors, except France 58.9M
# (2000) and Mexico 38.2M (1960), 3-5% off: borderline, excluded. batch3 #7
# "20 m³" is a multiplication error (out of scope).

# --- Numbers to inject errors into ------------------------------------------
# (batch, id, text, occurrence (1 = first), category)
INJECT = [
    # batch 4 (natural)
    ("batch4.json", 1, "41.6 million", 1, "population"),
    ("batch4.json", 2, "1.464 billion", 1, "population"),
    ("batch4.json", 2, "1.407 billion", 1, "population"),
    ("batch4.json", 2, "341.8 million", 1, "population"),
    ("batch4.json", 4, "9.32 miles", 1, "conversion"),
    ("batch4.json", 4, "160.93 km", 1, "conversion"),
    ("batch4.json", 4, "62.14 mph", 1, "conversion"),
    ("batch4.json", 4, "77°F", 1, "conversion"),
    ("batch4.json", 5, "341.8 million", 1, "population"),
    ("batch4.json", 6, "175.7 million", 1, "population"),
    ("batch4.json", 6, "255.2 million", 1, "population"),
    ("batch4.json", 6, "237.5 million", 1, "population"),
    ("batch4.json", 6, "212.8 million", 1, "population"),
    ("batch4.json", 7, "1.10 pounds", 1, "conversion"),
    ("batch4.json", 7, "0.53 US gallons", 1, "conversion"),
    ("batch4.json", 8, "83.5 million", 1, "population"),
    ("batch4.json", 8, "68.7 million", 1, "population"),
    ("batch4.json", 8, "58.9 million", 1, "population"),
    ("batch4.json", 9, "1,076.4 square feet", 1, "conversion"),
    ("batch4.json", 10, "27 million", 1, "population"),
    # batch 5 (natural)
    ("batch5.json", 1, "2.5 billion", 1, "population"),
    ("batch5.json", 1, "3.0 billion", 1, "population"),
    ("batch5.json", 1, "6.1 billion", 1, "population"),
    ("batch5.json", 1, "8.2 billion", 1, "population"),
    ("batch5.json", 2, "14 million", 1, "population"),
    ("batch5.json", 2, "18.2 million", 1, "population"),
    ("batch5.json", 2, "30.7 million", 1, "population"),
    ("batch5.json", 2, "39.7 million", 1, "population"),
    ("batch5.json", 3, "376 million", 1, "population"),
    ("batch5.json", 3, "1.05 billion", 1, "population"),
    ("batch5.json", 3, "1.45 billion", 1, "population"),
    ("batch5.json", 4, "544 million", 1, "population"),
    ("batch5.json", 4, "1.26 billion", 1, "population"),
    ("batch5.json", 4, "1.42 billion", 2, "population"),     # the 2024 figure
    # batch 3 (the correct conversions in those paragraphs)
    ("batch3.json", 1, "177°C", 1, "conversion"),
    ("batch3.json", 2, "7.46 miles", 1, "conversion"),
    ("batch3.json", 2, "62.14 mph", 1, "conversion"),
    ("batch3.json", 3, "86°F", 1, "conversion"),
    ("batch3.json", 4, "55.92 mph", 1, "conversion"),
    ("batch3.json", 4, "3.6 km/h", 1, "conversion"),
    ("batch3.json", 5, "11.02 lb", 1, "conversion"),
    ("batch3.json", 5, "68.04 kg", 1, "conversion"),
    ("batch3.json", 9, "4.02 km", 1, "conversion"),
    ("batch3.json", 9, "16.09 km", 1, "conversion"),
    ("batch3.json", 10, "0.75 litres", 1, "conversion"),
]


def _find(text, needle, occurrence):
    pos = -1
    for _ in range(occurrence):
        pos = text.index(needle, pos + 1)
    return pos


def mutate(written, factor):
    """'41.6 million' x0.7 -> '29.1 million': same style, number changed."""
    i = 0
    while i < len(written) and (written[i].isdigit() or written[i] in ",."):
        i += 1
    number, rest = written[:i], written[i:]
    decimals = len(number.split(".")[1]) if "." in number else 0
    value = float(number.replace(",", "")) * factor
    new = f"{value:,.{decimals}f}" if "," in number else f"{value:.{decimals}f}"
    assert new != number, written
    return new + rest


def build():
    items = []
    for batch in ("batch4.json", "batch5.json"):
        for pid, text in load(batch).items():
            items.append({"id": f"{batch[:-5]}#{pid}", "kind": "natural", "text": text,
                          "errors": []})
    for batch, pid, needle, category, note in CHATGPT_REAL:
        text = load(batch)[pid]
        items.append({"id": f"{batch[:-5]}#{pid}", "kind": "chatgpt", "text": text,
                      "errors": [{"text": needle, "start": _find(text, needle, 1),
                                  "category": category, "note": note}]})
    for n, (batch, pid, needle, occurrence, category) in enumerate(INJECT):
        original = load(batch)[pid]
        start = _find(original, needle, occurrence)
        wrong = mutate(needle, FACTORS[n % 2])
        text = original[:start] + wrong + original[start + len(needle):]
        items.append({"id": f"{batch[:-5]}#{pid}/inject{n + 1}", "kind": "injected",
                      "text": text,
                      "errors": [{"text": wrong, "start": start, "category": category,
                                  "note": f"was {needle!r}, changed x{FACTORS[n % 2]}"}]})
    return items


if __name__ == "__main__":
    items = build()
    (HERE / "benchmark.json").write_text(json.dumps(items, indent=2, ensure_ascii=False),
                                         "utf-8")
    kinds = {k: sum(1 for i in items if i["kind"] == k) for k in ("natural", "chatgpt", "injected")}
    errors = [e for i in items for e in i["errors"]]
    print(f"{len(items)} items: {kinds}")
    print(f"{len(errors)} known errors: "
          f"{sum(e['category'] == 'population' for e in errors)} population, "
          f"{sum(e['category'] == 'conversion' for e in errors)} conversion")
