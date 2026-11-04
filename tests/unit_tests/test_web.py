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


def test_web_chat_explains_a_missing_key(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MODEL", "anthropic/claude-haiku-5-5")
    app = testing.AppTest.from_file(APP).run()
    assert "ANTHROPIC_API_KEY is not set" in app.error[0].value
