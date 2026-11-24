"""Score ChatGPT's answers on the benchmark, the same way Hallucinope was scored.

A known error counts as found if ChatGPT listed that number. On the natural
paragraphs (every number assumed correct), each number it lists is a false-alarm
candidate, reviewed by hand like Hallucinope's.

Save ChatGPT's replies as benchmark/chatgpt/reply1.json ... reply8.json, then:
    python benchmark/chatgpt_score.py --details
"""

import argparse
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "chatgpt"
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def clean_json(raw: str):
    """Undo rich-text copy damage (&#x20;, trailing backslashes, code fences)."""
    raw = html.unescape(raw)
    raw = re.sub(r"\\\s*$", "", raw, flags=re.M)
    raw = re.sub(r"^\s*```(?:json)?\s*$", "", raw, flags=re.M)
    return json.loads(raw)


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "").lstrip("-") for n in NUMBER.findall(str(text))}


def load_replies(out=OUT):
    answers = {}
    for path in sorted(out.glob("reply*.json")):
        for entry in clean_json(path.read_text("utf-8")):
            answers[entry["id"].strip().upper()] = entry.get("wrong_numbers") or []
    return answers


def score(items, key, answers):
    by_id = {i["id"]: i for i in items}
    rows, missing = [], []
    for pid, item_id in key.items():
        if pid not in answers:
            missing.append(pid)
            continue
        item = by_id[item_id]
        listed = answers[pid]
        listed_numbers = [numbers_in(w.get("text", "")) for w in listed]
        used = set()
        for e in item["errors"]:
            target = numbers_in(e["text"])
            hit = next((k for k, nums in enumerate(listed_numbers) if nums & target), None)
            if hit is not None:
                used.add(hit)
            rows.append({"pid": pid, "id": item_id, "kind": item["kind"],
                         "category": e["category"], "text": e["text"],
                         "found": hit is not None})
        extras = [w for k, w in enumerate(listed) if k not in used]
        rows.append({"pid": pid, "id": item_id, "kind": item["kind"], "extras": extras})
    return rows, missing


def print_report(rows, missing, details):
    errors = [r for r in rows if "found" in r]
    print("\nChatGPT on the Hallucinope benchmark\n")
    print(f"{'errors':<12}{'n':>4}{'found':>12}{'missed':>12}")
    for label, keep in (("all", lambda r: True),
                        ("population", lambda r: r["category"] == "population"),
                        ("conversion", lambda r: r["category"] == "conversion"),
                        ("injected", lambda r: r["kind"] == "injected"),
                        ("chatgpt", lambda r: r["kind"] == "chatgpt")):
        chosen = [r for r in errors if keep(r)]
        found = sum(r["found"] for r in chosen)
        n = len(chosen) or 1
        print(f"{label:<12}{len(chosen):>4}{found:>7} {found / n:>4.0%}"
              f"{len(chosen) - found:>7} {(len(chosen) - found) / n:>4.0%}")
    natural = [r for r in rows if "extras" in r and r["kind"] == "natural"]
    flagged = sum(len(r["extras"]) for r in natural)
    print(f"\nNatural paragraphs: {flagged} numbers flagged as wrong "
          f"(false-alarm candidates) across {len(natural)} paragraphs")
    others = sum(len(r["extras"]) for r in rows if "extras" in r and r["kind"] != "natural")
    print(f"Other numbers flagged inside error paragraphs: {others} (to review)")
    if missing:
        print(f"\nWARNING: no answer for {len(missing)} paragraphs: {', '.join(missing)}")
    if details:
        print("\n--- every known error")
        for r in errors:
            print(f"{'FOUND' if r['found'] else 'MISS '} {r['pid']} {r['id']:<22} {r['text']!r}")
        print("\n--- numbers flagged that were not known errors (review each)")
        for r in rows:
            for w in r.get("extras", []):
                print(f"{r['pid']} {r['id']:<22} {w.get('text')!r} -> {w.get('correct_value')!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--round", default="", help="e.g. round2")
    args = parser.parse_args()
    folder = HERE / args.round if args.round else HERE
    items = json.loads((folder / "benchmark.json").read_text("utf-8"))
    key = json.loads((folder / "chatgpt" / "key.json").read_text("utf-8"))
    rows, missing = score(items, key, load_replies(folder / "chatgpt"))
    print_report(rows, missing, args.details)
