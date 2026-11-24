"""Run Hallucinope on the benchmark and score it.

For every known error, the verdict on the claim covering that number is:
  caught     red, WRONG
  flagged    amber, UNCONFIRMED (counts as found, reported separately)
  missed     judged correct, can't verify, or not detected as a claim at all
For natural paragraphs (every number assumed correct), any red verdict is a
FALSE ALARM candidate, reviewed by hand afterwards.

The code fingerprint (a hash of every source file) proves which version was
graded; the code was frozen before this script first ran.

    python benchmark/run.py               # summary
    python benchmark/run.py --details     # every error and every false alarm
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hallucinope.checks.population_claims import Verdict
from hallucinope.data.population import load
from hallucinope.report import check_text

HERE = Path(__file__).parent
SRC = HERE.parent / "src" / "hallucinope"


def code_fingerprint() -> str:
    h = hashlib.sha256()
    for path in sorted(SRC.rglob("*.py")):
        h.update(path.relative_to(SRC).as_posix().encode())
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))   # same on Windows and Linux
    return h.hexdigest()[:12]


def outcome(report, error) -> str:
    start, end = error["start"], error["start"] + len(error["text"])
    for c in report.checked:
        if c.start < end and start < c.end:
            return {Verdict.WRONG: "caught", Verdict.UNCONFIRMED: "flagged",
                    Verdict.CORRECT: "missed: judged correct",
                    Verdict.CANT_VERIFY: "missed: can't verify"}[c.verdict]
    return "missed: not detected"


def run(items, population):
    results = []
    for item in items:
        report = check_text(item["text"], population)
        error_spans = [(e["start"], e["start"] + len(e["text"])) for e in item["errors"]]
        other_reds = [c for c in report.checked if c.verdict is Verdict.WRONG
                      and not any(c.start < e and s < c.end for s, e in error_spans)]
        results.append({
            "id": item["id"], "kind": item["kind"],
            "errors": [{**e, "outcome": outcome(report, e)} for e in item["errors"]],
            "claims_checked": len(report.checked),
            "other_reds": [{"text": c.claim.text, "message": c.message} for c in other_reds],
            "ambers": sum(c.verdict is Verdict.UNCONFIRMED for c in report.checked),
        })
    return results


def summarise(results) -> dict:
    errors = [(r["kind"], e) for r in results for e in r["errors"]]
    by = {}
    for label, keep in (("all", lambda k, e: True),
                        ("population", lambda k, e: e["category"] == "population"),
                        ("conversion", lambda k, e: e["category"] == "conversion"),
                        ("injected", lambda k, e: k == "injected"),
                        ("chatgpt", lambda k, e: k == "chatgpt")):
        chosen = [e for k, e in errors if keep(k, e)]
        counts = Counter(e["outcome"] for e in chosen)
        by[label] = {"errors": len(chosen), "caught": counts["caught"],
                     "flagged": counts["flagged"],
                     "missed": len(chosen) - counts["caught"] - counts["flagged"],
                     "outcomes": dict(counts)}
    natural = [r for r in results if r["kind"] == "natural"]
    claims = sum(r["claims_checked"] for r in natural)
    false_alarms = sum(len(r["other_reds"]) for r in natural)
    return {"errors": by, "natural_claims_checked": claims,
            "natural_false_alarms": false_alarms,
            "natural_ambers": sum(r["ambers"] for r in natural),
            "other_reds_in_error_items": sum(len(r["other_reds"]) for r in results
                                             if r["kind"] != "natural")}


def print_summary(s, fingerprint):
    print(f"\nHallucinope benchmark   (code fingerprint {fingerprint})\n")
    print(f"{'errors':<12}{'n':>4}{'caught (red)':>15}{'flagged (amber)':>18}{'missed':>9}")
    for label, d in s["errors"].items():
        n = d["errors"] or 1
        print(f"{label:<12}{d['errors']:>4}{d['caught']:>8} {d['caught']/n:>5.0%}"
              f"{d['flagged']:>11} {d['flagged']/n:>5.0%}{d['missed']:>5} {d['missed']/n:>4.0%}")
    c, fa = s["natural_claims_checked"], s["natural_false_alarms"]
    print(f"\nNatural paragraphs: {c} claims checked, {fa} red "
          f"({fa / (c or 1):.1%} false-alarm candidates), {s['natural_ambers']} amber")
    print(f"Other red verdicts inside error paragraphs: {s['other_reds_in_error_items']} "
          "(to review)")


def print_details(results):
    print("\n--- every known error")
    for r in results:
        for e in r["errors"]:
            mark = {"caught": "RED  ", "flagged": "AMBER"}.get(e["outcome"], "MISS ")
            print(f"{mark} {r['id']:<22} {e['text']!r:<24} {e['outcome']:<24} {e['note']}")
    print("\n--- red verdicts on numbers assumed correct (review each)")
    for r in results:
        for o in r["other_reds"]:
            print(f"{r['id']:<22} {o['text']!r}: {o['message']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--round", default="",
                        help="e.g. round2 to use benchmark/round2/benchmark.json")
    args = parser.parse_args()
    folder = HERE / args.round if args.round else HERE
    items = json.loads((folder / "benchmark.json").read_text("utf-8"))
    fingerprint = code_fingerprint()
    results = run(items, load())
    summary = summarise(results)
    out = folder / f"results_{fingerprint}.json"
    out.write_text(json.dumps({"fingerprint": fingerprint, "summary": summary,
                               "results": results}, indent=2, ensure_ascii=False), "utf-8")
    print_summary(summary, fingerprint)
    if args.details:
        print_details(results)
    print(f"\nFull results saved to {out}")
