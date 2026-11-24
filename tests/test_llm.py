"""Tests for the model connection and output validation. No Ollama needed."""

import json

import pytest

from hallucinope import config
from hallucinope.llm.base import LLMError, validate
from hallucinope.llm.ollama import OllamaHTTPError, OllamaModel

SCHEMA = {
    "type": "object",
    "properties": {
        "country": {"type": "string"},
        "year": {"type": ["integer", "null"]},
        "comparator": {"type": "string", "enum": ["about", "over", "under"]},
    },
    "required": ["country", "year", "comparator"],
}
GOOD = {"country": "Canada", "year": 2025, "comparator": "about"}


class FakeOllama:
    """Records requests and replies the way Ollama's /api/chat does."""

    def __init__(self, content=json.dumps(GOOD), error=None, reject_think=False):
        self.content, self.error, self.reject_think = content, error, reject_think
        self.requests = []

    def __call__(self, url, body):
        self.requests.append((url, body))
        if self.reject_think and "think" in body:
            raise OllamaHTTPError(400, '{"error":"invalid option: think"}')
        if self.error:
            raise self.error
        return {"model": body["model"], "done": True,
                "message": {"role": "assistant", "content": self.content}}


def ask(fake, model="qwen3.5:0.8b"):
    return OllamaModel(model, "http://localhost:11434", post=fake).complete_json(
        "system prompt", "user prompt", SCHEMA)


def test_returns_validated_answer():
    assert ask(FakeOllama()) == GOOD


def test_request_is_constrained_and_repeatable():
    fake = FakeOllama()
    ask(fake)
    url, body = fake.requests[0]
    assert url == "http://localhost:11434/api/chat"
    assert body["format"] == SCHEMA            # structured output
    assert body["options"]["temperature"] == 0  # repeatable answers
    assert body["stream"] is False and body["think"] is False
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_retries_without_think_when_unsupported():
    fake = FakeOllama(reject_think=True)
    assert ask(fake) == GOOD
    assert "think" not in fake.requests[-1][1]


def test_missing_model_says_how_to_download_it():
    fake = FakeOllama(error=OllamaHTTPError(404, '{"error":"model not found"}'))
    with pytest.raises(LLMError, match="ollama pull qwen3.5:0.8b"):
        ask(fake)


def test_ollama_not_running_is_a_clear_error():
    fake = FakeOllama(error=LLMError("[LLM:Ollama] can't reach Ollama. Is the Ollama app running?"))
    with pytest.raises(LLMError, match="Is the Ollama app running"):
        ask(fake)


@pytest.mark.parametrize("content", ["", "not json", '{"country": "Canada"}',
                                     '{"country": "Canada", "year": "2025", "comparator": "about"}',
                                     '{"country": "Canada", "year": 2025, "comparator": "roughly"}'])
def test_bad_model_output_is_rejected(content):
    with pytest.raises(LLMError):
        ask(FakeOllama(content=content))


# --- validate() on its own --------------------------------------------------

@pytest.mark.parametrize("value", [
    GOOD,
    {"country": "Canada", "year": None, "comparator": "over"},
])
def test_validate_accepts(value):
    validate(value, SCHEMA)


@pytest.mark.parametrize("value", [
    {"country": "Canada", "year": True, "comparator": "about"},   # bool is not a year
    {"country": 5, "year": 2025, "comparator": "about"},
    [GOOD],
])
def test_validate_rejects(value):
    with pytest.raises(LLMError):
        validate(value, SCHEMA)


def test_validate_checks_list_items():
    schema = {"type": "array", "items": {"type": "integer"}}
    validate([1, 2], schema)
    with pytest.raises(LLMError, match=r"\$\[1\]"):
        validate([1, "two"], schema)


# --- settings ---------------------------------------------------------------

def test_model_defaults_and_can_be_swapped(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HALLUCINOPE_LLM_MODEL", raising=False)
    assert config.llm_model() == "qwen3.5:0.8b"
    (tmp_path / ".env").write_text("HALLUCINOPE_LLM_MODEL=qwen3.5:2b\n", encoding="utf-8")
    assert config.llm_model() == "qwen3.5:2b"
    monkeypatch.setenv("HALLUCINOPE_LLM_MODEL", "llama3.2:1b")
    assert config.llm_model() == "llama3.2:1b"


def test_ollama_url_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HALLUCINOPE_OLLAMA_URL", raising=False)
    assert config.ollama_url() == "http://localhost:11434"
