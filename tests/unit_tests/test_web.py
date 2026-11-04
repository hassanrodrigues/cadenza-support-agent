from datetime import date, time

import pytest
from langchain_core.messages import AIMessage

from cadenza import graph, prompts
from cadenza.context import ROOT_DIR

testing = pytest.importorskip("streamlit.testing.v1")
APP = str(ROOT_DIR / "src" / "cadenza" / "web.py")


def test_web_chat_greets_and_shows_the_reply_with_money_escaped(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("EMPORIO_NOW", "2026-02-20T10:00")
    monkeypatch.setattr(
        graph,
        "run_turn",
        lambda text, context, thread: [AIMessage("Sai por R$ 2.199,00")],
    )
    app = testing.AppTest.from_file(APP).run()
    assert app.chat_message[0].markdown[0].value == prompts.GREETING
    app.chat_input[0].set_value("Quanto custa o Takamine GD20?").run()
    assert [m.markdown[0].value for m in app.chat_message[1:]] == [
        "Quanto custa o Takamine GD20?",
        r"Sai por R\$ 2.199,00",
    ]


def test_suggestion_click_is_sent_like_a_typed_message(monkeypatch):
    sent = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(
        graph,
        "run_turn",
        lambda text, context, thread: sent.append(text) or [AIMessage("ok")],
    )
    app = testing.AppTest.from_file(APP).run()
    app.button(key="suggestion-1").click().run()
    assert sent == [prompts.WEB_SUGGESTIONS[1]]
    assert not [b for b in app.button if b.key and b.key.startswith("suggestion")]


def test_store_clock_defaults_to_the_dataset_and_a_new_time_starts_over(monkeypatch):
    seen = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("EMPORIO_NOW", "")
    monkeypatch.setattr(
        graph,
        "run_turn",
        lambda text, context, thread: seen.append(context.now) or [AIMessage("ok")],
    )
    app = testing.AppTest.from_file(APP).run()
    assert app.success[0].value == "Store open now"  # Friday 20/02/2026 10:00
    app.date_input[0].set_value(date(2026, 2, 21)).run()
    app.time_input[0].set_value(time(15, 0)).run()
    assert app.info[0].value == "Store closed; the team is back Mon 23/02 at 09:00"
    app.chat_input[0].set_value("oi").run()
    assert [f"{now:%d/%m/%Y %H:%M}" for now in seen] == ["21/02/2026 15:00"]


def test_each_reply_shows_the_tools_it_called(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    call = {"name": "get_product_details", "args": {"name_or_id": "GD20"}, "id": "1"}
    monkeypatch.setattr(
        graph,
        "run_turn",
        lambda text, context, thread: [
            AIMessage("", tool_calls=[call]),
            AIMessage("Sai por R$ 2.199,00"),
        ],
    )
    app = testing.AppTest.from_file(APP).run()
    app.chat_input[0].set_value("Quanto custa?").run()
    assert app.code[0].value == 'get_product_details(name_or_id="GD20")'


def test_web_chat_explains_a_missing_key(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MODEL", "anthropic/claude-haiku-5-5")
    app = testing.AppTest.from_file(APP).run()
    assert "ANTHROPIC_API_KEY is not set" in app.error[0].value
