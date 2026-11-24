"""Comparison words before a number: "roughly", "more than", "under"...

A fixed, short list, so rules do this perfectly. (In testing, the 0.8B
model labelled "roughly 41 million" as "over"; this is why it isn't asked.)
"""

from __future__ import annotations

import re

from ..checks.population_claims import Comparator

PHRASES = {
    Comparator.OVER: ["more than", "over", "above", "at least", "upwards of", "in excess of",
                      "exceeds", "exceeded", "exceeding", "exceed", "surpasses", "surpassed",
                      "surpass", "tops", "topped", "passes", "passed", "pass"],
    Comparator.UNDER: ["fewer than", "less than", "under", "below", "at most", "just under",
                       "not quite"],
    Comparator.ABOUT: ["about", "roughly", "approximately", "around", "nearly", "almost",
                       "some", "circa", "close to", "an estimated", "estimated", "~"],
}
_FILLER = r"(?:\s+(?:a|an|the|just|some|well|population\s+of))*"


def comparator_before(text: str, number_start: int) -> Comparator:
    """The comparison stated just before a number; ABOUT if none."""
    window = text[max(0, number_start - 40):number_start].lower().rstrip()
    best: tuple[int, Comparator] | None = None
    for comparator, phrases in PHRASES.items():
        for phrase in phrases:
            pattern = (r"(?:^|\W)" if phrase[0].isalnum() else "") + re.escape(phrase) + \
                      _FILLER + r"$"
            m = re.search(pattern, window)
            if m and (best is None or len(phrase) > best[0]):
                best = (len(phrase), comparator)   # longest phrase wins: "just under"
    return best[1] if best else Comparator.ABOUT
