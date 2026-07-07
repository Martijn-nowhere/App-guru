"""Tests for .env loading (the convenience so keys don't have to be
exported by hand each session)."""

import os

import app_guru.cli as cli


def test_load_env_reads_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "GOOGLE_SEARCH_API_KEY=from_dotenv\n"
        "GOOGLE_SEARCH_CX=cx_from_dotenv\n"
        "ANTHROPIC_API_KEY=ak_from_dotenv\n"
    )
    monkeypatch.chdir(tmp_path)
    for key in ("GOOGLE_SEARCH_API_KEY", "GOOGLE_SEARCH_CX", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    cli.load_env()

    assert os.environ["GOOGLE_SEARCH_API_KEY"] == "from_dotenv"
    assert os.environ["GOOGLE_SEARCH_CX"] == "cx_from_dotenv"
    assert os.environ["ANTHROPIC_API_KEY"] == "ak_from_dotenv"


def test_real_env_var_overrides_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GOOGLE_SEARCH_API_KEY=from_dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "from_real_env")

    cli.load_env()

    # override=False means an already-set real env var wins over the .env file
    assert os.environ["GOOGLE_SEARCH_API_KEY"] == "from_real_env"


def test_load_env_no_dotenv_is_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .env here
    # should not raise
    cli.load_env()
