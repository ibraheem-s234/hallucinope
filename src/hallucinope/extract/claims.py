"""Paragraph -> claims. The pipeline approved for step 9:

  1. Rules find every number (numbers.py).
  2. Rules sort them: paired quantities become conversion claims; large
     counts near "people/population/residents..." become population claims;
     comparison words come from comparators.py.
  3. The model (optional) labels each population claim's country and year.
  4. Rules check the model: its country must be mentioned in the paragraph
     and its year must appear in it. Otherwise the rules' label is used.

Without a model, rules label everything (nearest country / same-sentence
year). Each claim records which method labelled it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..checks.population_claims import Comparator, PopulationClaim
from ..llm.base import JsonModel, LLMError
from .comparators import comparator_before
from .countries import CountryIndex, Mention
from .numbers import NumberSpan, find_numbers
from .places import place_mentions

POPULATION_WORDS = re.compile(
    r"\b(people|population|populations|populated|residents|inhabitants|citizens|"
    r"persons|home to|lives? in|lived in)\b", re.IGNORECASE)
MIN_POPULATION = 1_000
# Characters allowed between the two sides of a conversion:
# "90 km/h is equivalent to approximately 55.92 mph" needs about 40.
MAX_PAIR_GAP = 60
MIN_UNCHECKED_COUNT = 1_000  # smaller bare numbers are left out of the summary
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“(])")

DESCRIBES = ["a country", "a city or region", "something else"]
LABEL_SYSTEM = (
    "You label one number in a paragraph. The number is marked like [[this]]. "
    "Reply only with JSON. "
    "'describes': is the marked number the population of a whole country, of a "
    "city or region, or something else? "
    "'country': which country's population it is, chosen from the list. "
    "'year': the year the marked number refers to, chosen from the list, or null "
    "if the paragraph does not say."
)


def label_schema(country_names: list[str], years: list[int]) -> dict:
    """Answers are restricted to what's in this paragraph: the model chooses
    from lists, so it can't name a country or year the text doesn't contain."""
    return {
        "type": "object",
        "properties": {
            "describes": {"type": "string", "enum": DESCRIBES},
            "country": {"type": ["string", "null"], "enum": country_names + [None]},
            "year": {"type": ["integer", "null"], "enum": years + [None]},
        },
        "required": ["describes", "country", "year"],
    }


@dataclass(frozen=True)
class ConversionClaim:
    value: float
    unit: str
    stated_value: float
    stated_unit: str


@dataclass(frozen=True)
class Claim:
    start: int                     # position in the paragraph, for highlighting
    end: int
    text: str
    kind: str                      # "population" | "conversion"
    population: PopulationClaim | None = None
    conversion: ConversionClaim | None = None
    labelled_by: str = "rules"     # "rules" | "model" | "rules (model answer rejected)"


@dataclass
class Extraction:
    text: str
    claims: list[Claim] = field(default_factory=list)
    unchecked: list[NumberSpan] = field(default_factory=list)  # for the summary line
    model_errors: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[tuple[int, int]]:
    bounds, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        bounds.append((start, m.start()))
        start = m.end()
    bounds.append((start, len(text)))
    return bounds


def _sentence_of(pos: int, sentences: list[tuple[int, int]]) -> tuple[int, int]:
    return next((s for s in sentences if s[0] <= pos <= s[1]), sentences[-1])


# Words that link the two sides of a conversion ("is equivalent to approximately").
CONVERSION_CUES = re.compile(
    r"[(=≈~]|\b(is|are|was|equals?|equal|equivalent|approximately|approx|about|roughly|"
    r"around|or|i\.e|means|gives|corresponds|converts?|translates|becomes|holds|weighs|"
    r"indicates|works out)\b", re.IGNORECASE)
# Words that mean two quantities are separate things, not a conversion:
# "5 m by 4 m", "30 g of butter and 15 g of sugar", "190 lb, while ... 5 kg".
NOT_A_CONVERSION = re.compile(
    r"[×–]|\b(by|and|while|but|whereas|plus|versus|vs|than|per|times|each|then|"
    r"after|before|compared|meaning|x)\b", re.IGNORECASE)


def _same_unit(a: NumberSpan, b: NumberSpan) -> bool:
    """'5 m' and '4 metres' are the same unit, so they can't be a conversion."""
    return (abs(a.unit.scale - b.unit.scale) <= 1e-12 * max(a.unit.scale, b.unit.scale)
            and a.unit.offset == b.unit.offset)


def _pair_conversions(spans: list[NumberSpan], text: str) -> list[tuple[NumberSpan, NumberSpan]]:
    """Two adjacent quantities form a conversion only if they measure the same
    kind of thing in DIFFERENT units, close together in one sentence, linked by
    conversion wording and not by list or comparison words."""
    pairs, used = [], set()
    for a, b in zip(spans, spans[1:]):
        if not (a.kind == b.kind == "quantity" and id(a) not in used
                and a.unit.dimension == b.unit.dimension and not _same_unit(a, b)):
            continue
        gap = text[a.end:b.start]
        if (0 <= len(gap) <= MAX_PAIR_GAP and not re.search(r"[.!?;]\s", gap)
                and CONVERSION_CUES.search(gap) and not NOT_A_CONVERSION.search(gap)):
            pairs.append((a, b))
            used.update((id(a), id(b)))
    return pairs


POPULATION_NOUNS = {"people", "persons", "residents", "inhabitants", "citizens", "souls"}
CENSUS = re.compile(r"\bcensus\b", re.IGNORECASE)


def _counts_something_else(text: str, span: NumberSpan) -> bool:
    """True if a different plural noun follows the number ('5 million tourists'),
    or it's a rate ('1,193 people per square kilometre', '50,000 per capita')."""
    if re.match(r"\s+(?:[A-Za-z]+\s+)?per\b", text[span.end:], re.IGNORECASE):
        return True
    m = re.match(r"\s+([A-Za-z]+)", text[span.end:])
    if not m:
        return False
    word = m.group(1).lower()
    return word.endswith("s") and word not in POPULATION_NOUNS and len(word) > 3


def _rules_label(span: NumberSpan, mentions: list[Mention], years: list[NumberSpan],
                 sentence: tuple[int, int], separated: Callable[[int, int], bool]
                 ) -> tuple[str | None, int | None]:
    """Nearest country (same sentence first, then earlier), and its year."""
    in_sentence = [m for m in mentions if sentence[0] <= m.start <= sentence[1]]
    before = [m for m in mentions if m.end <= span.start]
    country = None
    # The subject usually comes first: "France had 67 million, while India..."
    in_sentence_before = [m for m in in_sentence if m.end <= span.start]
    if in_sentence_before:
        country = in_sentence_before[-1].iso3
    elif in_sentence:
        country = in_sentence[0].iso3
    elif before:
        country = before[-1].iso3
    return country, _rules_year(span, years, sentence, separated)


YEAR_AFTER_WINDOW = 25   # "103.4 million in 1970", "110 million people, according to 2023"
CLAUSE_BREAK = re.compile(r"\b(and|but|while|whereas)\b|;", re.IGNORECASE)


def _rules_year(span: NumberSpan, years: list[NumberSpan], sentence: tuple[int, int],
                separated: Callable[[int, int], bool]) -> int | None:
    """The year a number refers to, from its own sentence.

    1. A year right after it wins: "93.2 million in 1960 and 103.4 million in
       1970" gives 1970 to 103.4 million, not the nearer-looking 1960.
    2. Otherwise the nearest year before it: "By 2025, it had fallen to 123.4M".
    3. Otherwise none (the claim is about "now"). A year later in the sentence
       usually belongs to something else: "52 million citizens, but fewer than
       250,000 babies were born in 2023".
    """
    same = [y for y in years if sentence[0] <= y.start <= sentence[1]]
    after = [y for y in same if 0 <= y.start - span.end <= YEAR_AFTER_WINDOW
             and not separated(span.end, y.start)]
    if after:
        return int(after[0].value)
    before = [y for y in same if y.end <= span.start]
    return int(before[-1].value) if before else None


def _about_a_place(span: NumberSpan, sentence: tuple[int, int], mentions: list[Mention],
                   places: list[tuple[int, int, str]]) -> bool:
    """True if the number is about a province, state or city, not a country.

    Errs towards True (the claim goes to "not checked"), because checking a
    city's population against its country's is a guaranteed false alarm.
    """
    in_sentence = [p for p in places if sentence[0] <= p[0] <= sentence[1]]
    if not in_sentence:
        return False
    if any(p[1] <= span.start for p in in_sentence):
        return True                       # "Quebec had 9,067,114 people"
    countries_before = [m for m in mentions if sentence[0] <= m.start and m.end <= span.start]
    return not countries_before           # "3 million live in Toronto, Canada's..."


def _model_label(model: JsonModel, text: str, span: NumberSpan, countries: CountryIndex,
                 mentions: list[Mention], years_in_text: set[int]
                 ) -> tuple[str, str | None, int | None]:
    """Ask the model, then check its answer against the text.

    Returns (status, iso3, year), where status is:
      "accepted"     a country (and year, if any) that appear in the text
      "rejected"     an answer that fails the checks (rules' label is used)
      "not_country"  it says the number is a city's, region's or something
                     else's. The model may remove a claim, never add one.
    """
    names = list(dict.fromkeys(m.text for m in mentions))      # unique, in order
    years = sorted(years_in_text)
    marked = f"{text[:span.start]}[[{text[span.start:span.end]}]]{text[span.end:]}"
    answer = model.complete_json(LABEL_SYSTEM, marked, label_schema(names, years))
    if answer["describes"] != "a country":
        return "not_country", None, None
    iso3 = countries.resolve(answer["country"]) if answer["country"] else None
    year = answer["year"]
    # The schema already restricts answers to these lists; checked again here
    # because a model connection that ignores the schema must not slip through.
    if iso3 is None or iso3 not in {m.iso3 for m in mentions} or \
            (year is not None and year not in years_in_text):
        return "rejected", None, None
    return "accepted", iso3, year


def extract(text: str, countries: CountryIndex, model: JsonModel | None = None) -> Extraction:
    result = Extraction(text)
    spans = find_numbers(text)
    sentences = _sentences(text)
    mentions = countries.mentions(text)
    years = [s for s in spans if s.kind == "year"]
    years_in_text = {int(y.value) for y in years}
    consumed: set[int] = set()

    for a, b in _pair_conversions(spans, text):
        consumed.update((id(a), id(b)))
        result.claims.append(Claim(
            a.start, b.end, text[a.start:b.end], "conversion",
            conversion=ConversionClaim(a.value, a.unit.symbol, b.value, b.unit.symbol)))

    places = place_mentions(text)

    def separated(a: int, b: int) -> bool:
        """Is a year at position b cut off from a number ending at position a?
        Yes if another population-sized number sits between them ("July 1, 2023"
        day numbers don't count), or a new clause starts: in "15.4 million, and
        by 2020 it was 19.3 million", 2020 belongs to 19.3 million."""
        return bool(CLAUSE_BREAK.search(text[a:b])) or any(
            a <= s.start and s.end <= b and s.kind == "count"
            and s.value >= MIN_POPULATION for s in spans)

    previous_was_population = False
    previous_sentence: tuple[int, int] | None = None
    for span in spans:
        if id(span) in consumed or span.kind != "count" or span.value < MIN_POPULATION:
            continue
        sentence = _sentence_of(span.start, sentences)
        if sentence != previous_sentence and previous_sentence is not None:
            previous_was_population = any(
                c.kind == "population" and previous_sentence[0] <= c.start <= previous_sentence[1]
                for c in result.claims)
        previous_sentence = sentence
        if _counts_something_else(text, span):
            continue          # "5 million tourists", "15,000 cars"
        if not (POPULATION_WORDS.search(text[sentence[0]:sentence[1]])
                or previous_was_population):
            continue
        if _about_a_place(span, sentence, mentions, places):
            continue          # a province, state or city: stays in "not checked"
        country, year = _rules_label(span, mentions, years, sentence, separated)
        labelled_by = "rules"
        if model is not None:
            try:
                status, m_country, m_year = _model_label(
                    model, text, span, countries, mentions, years_in_text)
                if status == "accepted":
                    country, year, labelled_by = m_country, m_year, "model"
                elif status == "rejected":
                    labelled_by = "rules (model answer rejected)"
                else:
                    continue  # not a country's population: stays in "not checked"
            except LLMError as exc:
                result.model_errors.append(str(exc))
                labelled_by = "rules (model unavailable)"
        if country is None:
            continue  # no country anywhere in the text: nothing to check against
        consumed.add(id(span))
        result.claims.append(Claim(
            span.start, span.end, span.text, "population",
            population=PopulationClaim(
                country, span.value, year, comparator_before(text, span.start), span.text,
                census=bool(CENSUS.search(text[sentence[0]:sentence[1]]))),
            labelled_by=labelled_by))

    result.claims.sort(key=lambda c: c.start)
    result.unchecked = [s for s in spans if id(s) not in consumed and s.kind != "year"
                        and not (s.kind == "count" and s.value < MIN_UNCHECKED_COUNT)]
    return result
