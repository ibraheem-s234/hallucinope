"""Check a paragraph from the command line.

    python -m hallucinope "Canada has about 38 million people."
    python -m hallucinope --file essay.txt
    python -m hallucinope                       (then paste text; Enter on an empty line to finish)
    python -m hallucinope --model "..."         (use the local AI for labelling)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import config
from .checks.population_claims import Verdict
from .data.models import DataSourceError
from .data.population import load
from .report import Report, check_text

LABELS = {Verdict.CORRECT: ("CORRECT", "32"), Verdict.WRONG: ("WRONG", "31"),
          Verdict.UNCONFIRMED: ("UNCONFIRMED", "33"), Verdict.CANT_VERIFY: ("CAN'T VERIFY", "90")}


def _paint(text: str, code: str, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


def render(report: Report, color: bool = False) -> str:
    """The paragraph with numbered markers, then one line per claim."""
    out, pos = [], 0
    for i, c in enumerate(report.checked, 1):
        label, code = LABELS[c.verdict]
        out.append(report.text[pos:c.start])
        out.append(_paint(f"{report.text[c.start:c.end]}[{i}]", code, color))
        pos = c.end
    out.append(report.text[pos:])
    lines = ["".join(out), ""]

    for i, c in enumerate(report.checked, 1):
        label, code = LABELS[c.verdict]
        # Messages start with their verdict ("Wrong: ..."); show it once, as the label.
        detail = c.message.split(": ", 1)[1] if ": " in c.message else c.message
        lines.append(f"[{i}] {_paint(label, code, color)}  {detail}")
        if c.figure:
            lines.append(f"     source: {c.figure.citation()}")
    if not report.checked:
        lines.append("No checkable claims found.")

    tally = ", ".join(f"{report.count(v)} {LABELS[v][0].lower()}" for v in LABELS
                      if report.count(v))
    if tally:
        lines += ["", f"Summary: {tally}."]
    if report.unchecked:
        n = len(report.unchecked)
        lines.append(f"{n} other number{'s' if n > 1 else ''} not checked: "
                     + ", ".join(s.text for s in report.unchecked))
    for note in report.notes:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hallucinope",
                                     description="Check the numbers in a paragraph.")
    parser.add_argument("text", nargs="?", help="the paragraph (or use --file, or paste)")
    parser.add_argument("--file", help="read the paragraph from a text file")
    parser.add_argument("--model", action="store_true",
                        help="label claims with the local AI (off by default)")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args(argv)

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        print("Paste the paragraph, then press Enter on an empty line:", file=sys.stderr)
        lines = []
        for line in sys.stdin:          # stops at an empty line, or end of input
            if not line.strip():
                break
            lines.append(line)
        text = "".join(lines)
    if not text.strip():
        print("Nothing to check.", file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    try:
        population = load()
    except DataSourceError as exc:
        print(f"No population data available. {exc}", file=sys.stderr)
        return 1

    model = None
    if args.model or config.use_llm():
        from .llm.ollama import OllamaModel
        model = OllamaModel()

    report = check_text(text.strip(), population, model=model)
    color = not args.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ
    print(render(report, color))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # never crash on "°" in old consoles
    if sys.platform == "win32":
        os.system("")                               # enables colors in Windows terminals
    sys.exit(main())
