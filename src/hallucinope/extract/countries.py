"""Find country mentions in text, so labels can be checked against the paragraph.

Full names and aliases ("Canada", "South Korea", "America") match regardless
of case. Short codes ("US", "UK", "CAN") only match in capitals, so the
pronoun "us" or the word "can" are never read as countries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..data.models import ALIASES
from ..data.population import Population


# "America" alone means the USA; after these words it's a continent or region.
_CONTINENT_PREFIX = re.compile(r"\b(south|north|central|latin)[\s-]+$", re.IGNORECASE)


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    iso3: str
    text: str


class CountryIndex:
    def __init__(self, names: dict[str, str], codes: dict[str, str]):
        """names: lowercase name -> ISO3. codes: uppercase code -> ISO3."""
        self.names = names
        self.codes = codes
        # Longest names first, so "South Korea" wins over "Korea".
        alternatives = sorted(names, key=len, reverse=True)
        self._name_re = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in alternatives) + r")\b", re.IGNORECASE)
        self._code_re = re.compile(
            r"\b(" + "|".join(re.escape(c) for c in sorted(codes, key=len, reverse=True))
            + r")\b")

    @classmethod
    def from_population(cls, population: Population) -> CountryIndex:
        names: dict[str, str] = {}
        codes: dict[str, str] = {}
        for data in (population.un, population.worldbank):  # World Bank names win
            if data is None:
                continue
            for iso3, s in data.series.items():
                names[s.country.name.lower()] = iso3
                codes[iso3] = iso3
        for alias, iso3 in ALIASES.items():
            if len(alias) > 3:
                names.setdefault(alias, iso3)
            else:
                codes.setdefault(alias.upper(), iso3)
        return cls(names, codes)

    def mentions(self, text: str) -> list[Mention]:
        found: list[Mention] = []
        for regex, table, fold in ((self._name_re, self.names, str.lower),
                                   (self._code_re, self.codes, str.upper)):
            for m in regex.finditer(text):
                if any(f.start < m.end() and m.start() < f.end for f in found):
                    continue  # overlaps a longer match already found
                if m.group().lower() == "america" and _CONTINENT_PREFIX.search(text[:m.start()]):
                    continue  # "South America" is a continent, not the USA
                found.append(Mention(m.start(), m.end(), table[fold(m.group())], m.group()))
        return sorted(found, key=lambda x: x.start)

    def resolve(self, name: str) -> str | None:
        """ISO3 for a name or code, or None."""
        name = " ".join(name.split())
        return self.names.get(name.lower()) or self.codes.get(name.upper())
