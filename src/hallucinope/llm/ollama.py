"""A local model through Ollama: free, offline, nothing leaves the laptop.

Uses Ollama's /api/chat with a JSON schema in "format", which constrains
the model to output exactly the requested fields (structured outputs).
Temperature 0 makes answers repeatable. "think": false turns off the
reasoning mode some models (e.g. Qwen) have, which would only add delay;
if the installed Ollama or model rejects that option, we retry without it.

    python -m hallucinope.llm.ollama     # check the model works, and how fast
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from .. import config
from .base import LLMError, validate

TIMEOUT_SECONDS = 120   # the first request also loads the model into memory

# Poster: (url, body) -> parsed JSON. Injected so tests run without Ollama.
Poster = Callable[[str, dict], dict]


def http_post_json(url: str, body: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise OllamaHTTPError(exc.code, detail) from exc
    except (urllib.error.URLError, ConnectionError) as exc:
        raise LLMError("[LLM:Ollama] can't reach Ollama. Is the Ollama app running? "
                       f"({exc})") from exc
    except TimeoutError as exc:
        raise LLMError(f"[LLM:Ollama] no answer within {TIMEOUT_SECONDS}s") from exc
    except json.JSONDecodeError as exc:
        raise LLMError("[LLM:Ollama] response was not JSON") from exc


class OllamaHTTPError(LLMError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"[LLM:Ollama] HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class OllamaModel:
    def __init__(self, model: str | None = None, base_url: str | None = None,
                 post: Poster = http_post_json):
        self.name = model or config.llm_model()
        self.base_url = base_url or config.ollama_url()
        self._post = post

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        body = {
            "model": self.name,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
            "think": False,
        }
        url = f"{self.base_url}/api/chat"
        try:
            response = self._post(url, body)
        except OllamaHTTPError as exc:
            if exc.status == 404 or "not found" in exc.detail.lower():
                raise LLMError(f"[LLM:Ollama] model {self.name!r} isn't downloaded. "
                               f"Run: ollama pull {self.name}") from exc
            if "think" not in exc.detail.lower():
                raise
            body.pop("think")                       # older Ollama or model: retry
            response = self._post(url, body)

        content = (response.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("[LLM:Ollama] the model returned an empty answer")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"[LLM:Ollama] the model's answer wasn't valid JSON: "
                           f"{content[:200]!r}") from exc
        validate(data, schema)
        return data


if __name__ == "__main__":
    import sys

    model = OllamaModel()
    sentence = "Canada had a population of roughly 41 million people in 2025."
    schema = {
        "type": "object",
        "properties": {
            "country": {"type": "string"},
            "year": {"type": ["integer", "null"]},
            "comparator": {"type": "string", "enum": ["about", "over", "under"]},
        },
        "required": ["country", "year", "comparator"],
    }
    print(f"Model: {model.name}  at {model.base_url}")
    print(f"Sentence: {sentence}")
    start = time.perf_counter()
    try:
        answer = model.complete_json(
            "You label numeric claims. Reply only with the requested JSON fields.",
            f"For the number in this sentence, give the country it describes, the "
            f"year (or null), and whether it is stated as about, over or under.\n\n"
            f"{sentence}", schema)
    except LLMError as exc:
        print(f"Failed. {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Answer: {answer}")
    print(f"Valid labels in {time.perf_counter() - start:.1f}s")
