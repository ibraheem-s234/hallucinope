"""Make the prompts for the ChatGPT head-to-head (step 13).

The same 78 benchmark paragraphs go to ChatGPT, 10 per prompt, with neutral
IDs (P01-P78) so nothing reveals which paragraphs were altered. Versions of
the same source paragraph (an original and its altered copies) never share a
prompt, so ChatGPT can't find an error just by comparing two copies.

    python benchmark/chatgpt_prompts.py   # writes benchmark/chatgpt/prompt1.txt ...
"""

import json
import random
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "chatgpt"
PER_PROMPT = 10
SEED = 2026

INSTRUCTIONS = """\
Below are {n} short paragraphs. Check every number in them. For each paragraph, list
every number that is factually wrong: wrong population figures, wrong unit conversions,
or wrong arithmetic. Ignore small rounding differences. Answer from your own knowledge;
do not search the web.

Output ONLY valid JSON, no other text: a list with one object per paragraph, each with
"id" (for example "P07") and "wrong_numbers": a list of objects with "text" (the wrong
number exactly as it is written in the paragraph) and "correct_value". If every number
in a paragraph is correct, use an empty list.

"""


def source_of(item_id: str) -> str:
    return item_id.split("/")[0]          # "batch4#2/inject3" -> "batch4#2"


def assign(items):
    """Shuffle, then place each item in the emptiest prompt that has no other
    version of the same source paragraph."""
    rng = random.Random(SEED)
    order = items[:]
    rng.shuffle(order)
    n_prompts = -(-len(items) // PER_PROMPT)
    prompts = [[] for _ in range(n_prompts)]
    for item in sorted(order, key=lambda i: -sum(source_of(j["id"]) == source_of(i["id"])
                                                 for j in items)):
        options = [p for p in prompts if len(p) < PER_PROMPT
                   and all(source_of(x["id"]) != source_of(item["id"]) for x in p)]
        min(options, key=len).append(item)
    for p in prompts:
        rng.shuffle(p)
    return prompts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--round", default="", help="e.g. round2")
    args = parser.parse_args()
    folder = HERE / args.round if args.round else HERE
    OUT = folder / "chatgpt"
    items = json.loads((folder / "benchmark.json").read_text("utf-8"))
    prompts = assign(items)
    OUT.mkdir(exist_ok=True)
    key, n = {}, 0
    for k, group in enumerate(prompts, 1):
        lines = [INSTRUCTIONS.format(n=len(group))]
        for item in group:
            n += 1
            pid = f"P{n:02d}"
            key[pid] = item["id"]
            lines.append(f"{pid}: {item['text']}\n")
        (OUT / f"prompt{k}.txt").write_text("\n".join(lines), "utf-8")
    (OUT / "key.json").write_text(json.dumps(key, indent=2), "utf-8")
    print(f"{len(prompts)} prompts for {n} paragraphs written to {OUT}")
