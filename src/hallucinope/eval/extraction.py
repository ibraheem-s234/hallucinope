"""Score claim extraction on 20 hand-labelled paragraphs, per method.

A population claim counts as correct only if it was found AND its country,
year and comparison are all right. False positives are claims extracted
that shouldn't be (a city, tourists...): those would produce wrong verdicts.

    python -m hallucinope.eval.extraction                        # rules + default model
    python -m hallucinope.eval.extraction --models qwen3.5:0.8b,qwen3.5:2b
    python -m hallucinope.eval.extraction --verbose              # list every mistake
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..extract.claims import extract
from ..extract.countries import CountryIndex
from ..llm.base import JsonModel

CASES_FILE = Path(__file__).with_name("extraction_cases.json")


@dataclass
class Score:
    method: str
    expected: int = 0
    correct: int = 0
    false_positives: int = 0
    conversions_expected: int = 0
    conversions_found: int = 0
    seconds: float = 0.0
    paragraphs: int = 0
    mistakes: list[str] = field(default_factory=list)
    model_errors: int = 0

    def row(self) -> str:
        per = self.seconds / self.paragraphs if self.paragraphs else 0
        return (f"{self.method:<22} {self.correct:>3}/{self.expected:<3} "
                f"{self.correct / self.expected if self.expected else 0:>6.0%}   "
                f"{self.false_positives:>3}        "
                f"{self.conversions_found}/{self.conversions_expected:<6} {per:>6.1f}s")


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def score(method: str, cases: list[dict], countries: CountryIndex,
          model: JsonModel | None = None) -> Score:
    s = Score(method)
    for case in cases:
        start = time.perf_counter()
        result = extract(case["text"], countries, model)
        s.seconds += time.perf_counter() - start
        s.paragraphs += 1
        s.model_errors += len(result.model_errors)

        found = {c.text: c.population for c in result.claims if c.kind == "population"}
        for exp in case["population"]:
            s.expected += 1
            got = found.pop(exp["text"], None)
            if got is None:
                s.mistakes.append(f"missed {exp['text']!r} in: {case['text']}")
                continue
            wrong = [f"{k}={v!r} (expected {exp[k]!r})" for k, v in
                     (("country", got.country), ("year", got.year),
                      ("comparator", got.comparator.value)) if v != exp[k]]
            if wrong:
                s.mistakes.append(f"{exp['text']!r}: {', '.join(wrong)}")
            else:
                s.correct += 1
        for text in found:
            s.false_positives += 1
            s.mistakes.append(f"false positive {text!r} in: {case['text']}")

        conversions = {c.text.split(" (")[0].split(",")[0] for c in result.claims
                       if c.kind == "conversion"}
        for text in case.get("conversions", []):
            s.conversions_expected += 1
            s.conversions_found += any(c.startswith(text) for c in conversions)
    return s


def print_table(scores: list[Score], verbose: bool = False) -> None:
    print(f"\n{'method':<22} {'claims fully right':<19} {'false +':<10} "
          f"{'conversions':<12} {'time/paragraph'}")
    for s in scores:
        print(s.row() + (f"   ({s.model_errors} model errors)" if s.model_errors else ""))
    if verbose:
        for s in scores:
            print(f"\n--- {s.method}: {len(s.mistakes)} mistakes")
            for m in s.mistakes:
                print("  " + m)


if __name__ == "__main__":
    import argparse

    from .. import config
    from ..data.population import load
    from ..llm.ollama import OllamaModel

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", default=config.llm_model(),
                        help="comma-separated Ollama models; empty for rules only")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    countries = CountryIndex.from_population(load())
    cases = load_cases()
    scores = [score("rules only", cases, countries)]
    for name in filter(None, (m.strip() for m in args.models.split(","))):
        print(f"Running {name} on {len(cases)} paragraphs...")
        scores.append(score(name, cases, countries, OllamaModel(name)))
    print_table(scores, args.verbose)
