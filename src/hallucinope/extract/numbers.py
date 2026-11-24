"""Find every number in a paragraph, with its exact position and meaning.

Pure rules, no model: a number is only ever reported if it is literally in
the text, so nothing downstream can work with a number that isn't there.

Each NumberSpan has a kind:
  count    "41 million", "41,651,653"         (may become a population claim)
  quantity "260 km", "20 °C", "60 mph"        (may become a conversion claim)
  percent  "25%", "3 percent"                 (not checked yet)
  money    "$2 billion", "40 dollars"         (not checked yet)
  year     "2025"                             (context for other claims)

Known limits: spelled-out numbers ("forty million") are not detected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..units.registry import OffsetUnitError, Unit, UnknownUnitError, parse_unit

SCALES = {"thousand": 1e3, "million": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9,
          "trillion": 1e12}
# Uppercase letters glued to a number: "40M", "1.4B".
ATTACHED_SCALES = {"K": 1e3, "M": 1e6, "B": 1e9}
# English words that are also unit symbols; only counted as units when glued
# to the number ("12in"), never in prose ("41 million in 2025").
AMBIGUOUS_UNITS = {"in", "st", "d", "t", "h", "s", "kn", "min", "yr"}   # not "L": "50 L"
# "pounds" is deliberately absent: without "£" it means weight ("5.2 pounds").
MONEY_WORDS = {"dollar", "dollars", "usd", "cad", "eur", "euros", "gbp"}

_NUMBER = re.compile(
    r"(?P<currency>[$€£])?\s?"
    r"(?<![\w.,])(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d,]\d)"
    r"(?P<attached>[KMB](?![a-zA-Z]))?"
)
_WORD = re.compile(r"\s*([^\s(),;:!?]+)")


@dataclass(frozen=True)
class NumberSpan:
    start: int
    end: int
    text: str            # exactly as written, e.g. "41.7 million"
    value: float         # 41_700_000.0
    kind: str            # count | quantity | percent | money | year
    unit: Unit | None = None


def _next_words(text: str, pos: int, n: int) -> list[tuple[str, int]]:
    """Up to n following words, each with the position just after it.

    Stops at the end of a sentence: in "by 2000. In 2020", the word "In"
    belongs to the next sentence and must never be read as "2000 inches".
    """
    words = []
    for _ in range(n):
        m = _WORD.match(text, pos)
        if not m:
            break
        word = m.group(1)
        stripped = word.rstrip(".")
        if not stripped:
            break                                  # a bare full stop: sentence over
        words.append((stripped, m.end() - (len(word) - len(stripped))))
        if word.endswith("."):
            break                                  # this word ends the sentence
        pos = m.end()
    return words


def _match_unit(text: str, pos: int, glued: bool) -> tuple[Unit, int] | None:
    """Longest run of 1-3 following words that parses as a unit."""
    words = _next_words(text, pos, 3)
    for n in range(len(words), 0, -1):
        candidate = " ".join(w for w, _ in words[:n])
        if n == 1 and candidate.lower() in AMBIGUOUS_UNITS and not glued:
            continue
        try:
            return parse_unit(candidate), words[n - 1][1]
        except (UnknownUnitError, OffsetUnitError):
            continue
    return None


DECADE_OFFSETS = {"early": 2, "mid": 5, "late": 8}


def _decade(text: str, raw: str, start: int, end: int) -> NumberSpan | None:
    """'2080s' -> year 2085; 'early 2030s' -> 2032; 'late 1990s' -> 1998."""
    if not (re.fullmatch(r"\d{3}0", raw) and 1500 <= int(raw) <= 2100
            and text[end:end + 1] == "s" and not text[end + 1:end + 2].isalpha()):
        return None
    m = re.search(r"\b(early|mid|late)[-\s]*$", text[:start], re.IGNORECASE)
    offset = DECADE_OFFSETS[m.group(1).lower()] if m else 5
    begin = m.start() if m else start
    return NumberSpan(begin, end + 1, text[begin:end + 1], int(raw) + offset, "year")


def find_numbers(text: str) -> list[NumberSpan]:
    spans = []
    for m in _NUMBER.finditer(text):
        raw = m.group("num")
        value = float(raw.replace(",", ""))
        start = m.start("currency") if m.group("currency") else m.start("num")
        end = m.end()
        kind = "money" if m.group("currency") else "count"
        unit = None

        decade = _decade(text, raw, start, end)
        if decade:
            spans.append(decade)
            continue

        if m.group("attached"):
            value *= ATTACHED_SCALES[m.group("attached")]
        else:
            words = _next_words(text, end, 1)
            if words and words[0][0].lower() in SCALES:
                value *= SCALES[words[0][0].lower()]
                end = words[0][1]

        following = _next_words(text, end, 2)
        first = following[0][0].lower() if following else ""
        second = following[1][0].lower() if len(following) > 1 else ""
        if text[end:end + 1] == "%":                      # "25%"
            kind, end = "percent", end + 1
        elif first == "percent":                          # "25 percent"
            kind, end = "percent", following[0][1]
        elif first == "per" and second == "cent":         # "25 per cent"
            kind, end = "percent", following[1][1]
        elif first in MONEY_WORDS:
            kind, end = "money", following[0][1]
        elif kind == "count":
            glued = end < len(text) and not text[end].isspace()
            match = _match_unit(text, end, glued)
            if match:
                unit, end = match
                kind = "quantity"
            elif (re.fullmatch(r"\d{4}", raw) and 1500 <= value <= 2100
                  and not m.group("attached") and end == m.end()):
                kind = "year"

        spans.append(NumberSpan(start, end, text[start:end], value, kind, unit))
    return spans
