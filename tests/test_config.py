"""Tests for reading the UN token. Tokens here are fake strings."""

import pytest

from hallucinope import config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv(config.UN_TOKEN_VAR, raising=False)
    monkeypatch.chdir(tmp_path)


def test_reads_token_from_env_file(tmp_path):
    (tmp_path / ".env").write_text("HALLUCINOPE_UN_TOKEN=abc123\n", encoding="utf-8")
    assert config.un_token() == "abc123"


def test_environment_variable_wins(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("HALLUCINOPE_UN_TOKEN=from-file\n", encoding="utf-8")
    monkeypatch.setenv(config.UN_TOKEN_VAR, "from-env")
    assert config.un_token() == "from-env"


@pytest.mark.parametrize("line", [
    "HALLUCINOPE_UN_TOKEN=Bearer abc123",
    'HALLUCINOPE_UN_TOKEN="abc123"',
    "HALLUCINOPE_UN_TOKEN = abc123 ",
])
def test_tolerates_common_formatting(tmp_path, line):
    (tmp_path / ".env").write_text(line + "\n", encoding="utf-8")
    assert config.un_token() == "abc123"


def test_tolerates_notepad_byte_order_mark(tmp_path):
    (tmp_path / ".env").write_text("﻿HALLUCINOPE_UN_TOKEN=abc123\n", encoding="utf-8")
    assert config.un_token() == "abc123"


def test_ignores_comments_and_other_keys(tmp_path):
    (tmp_path / ".env").write_text("# my secrets\nOTHER=x\nHALLUCINOPE_UN_TOKEN=abc\n",
                                   encoding="utf-8")
    assert config.un_token() == "abc"


def test_missing_token_returns_none():
    assert config.un_token() is None
