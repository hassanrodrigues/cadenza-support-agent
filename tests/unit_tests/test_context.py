from datetime import datetime

from cadenza.context import DEFAULT_MODEL, STORE_TZ, Context, parse_now


def test_model_defaults_to_haiku_when_env_is_unset(monkeypatch):
    monkeypatch.delenv("MODEL", raising=False)
    assert Context().model == DEFAULT_MODEL


def test_model_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("MODEL", "openai/gpt-x")
    assert Context().model == "openai/gpt-x"


def test_explicit_model_wins_over_env(monkeypatch):
    monkeypatch.setenv("MODEL", "openai/gpt-x")
    assert Context(model="anthropic/other").model == "anthropic/other"


def test_naive_now_is_read_as_store_time():
    now = parse_now("2026-02-20T10:00")
    assert now == datetime(2026, 2, 20, 10, 0, tzinfo=STORE_TZ)


def test_aware_now_is_converted_to_store_time():
    assert parse_now("2026-02-20T14:00+00:00").hour == 10


def test_empty_now_falls_back_to_current_store_time(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "")
    assert Context().now.tzinfo == STORE_TZ
