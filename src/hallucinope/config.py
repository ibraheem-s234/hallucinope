"""All settings read from the environment live here, and only here."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def cache_dir() -> Path:
    """Where downloaded data is stored.

    Override with HALLUCINOPE_CACHE_DIR. Defaults to the OS's per-user cache
    location, which is outside OneDrive/Dropbox so sync tools leave it alone.
    """
    override = os.environ.get("HALLUCINOPE_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "hallucinope"


UN_TOKEN_VAR = "HALLUCINOPE_UN_TOKEN"


def un_token(env_file: Path | None = None) -> str | None:
    """The UN Data Portal token, or None if it isn't configured.

    Checked in order: the HALLUCINOPE_UN_TOKEN environment variable, then a
    .env file in the current folder. A leading "Bearer " is stripped, so
    either form works. The token is never logged or printed.
    """
    raw = os.environ.get(UN_TOKEN_VAR)
    if not raw:
        raw = _read_env_file(env_file or Path(".env")).get(UN_TOKEN_VAR)
    if not raw:
        return None
    token = raw.strip().strip('"').strip("'")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token or None


DEFAULT_LLM_MODEL = "qwen3.5:0.8b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


def llm_model() -> str:
    """Which local model labels claims. Swap with HALLUCINOPE_LLM_MODEL."""
    return _setting("HALLUCINOPE_LLM_MODEL") or DEFAULT_LLM_MODEL


def ollama_url() -> str:
    """Where Ollama listens. Override with HALLUCINOPE_OLLAMA_URL."""
    return (_setting("HALLUCINOPE_OLLAMA_URL") or DEFAULT_OLLAMA_URL).rstrip("/")


def use_llm() -> bool:
    """Whether the local model labels claims. Off by default: in the step 9
    benchmark, rules scored 95% and the 0.8B/2B models 32-47%.
    Turn on with HALLUCINOPE_USE_LLM=1."""
    return (_setting("HALLUCINOPE_USE_LLM") or "").lower() in ("1", "true", "yes", "on")


def _setting(name: str) -> str | None:
    """A setting from the environment, falling back to .env in this folder."""
    value = os.environ.get(name) or _read_env_file(Path(".env")).get(name)
    if not value:
        return None
    return value.strip().strip('"').strip("'") or None


def _read_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=value parser for .env files (no extra dependency needed)."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")  # -sig: tolerate Notepad's BOM
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values
