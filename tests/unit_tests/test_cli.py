import io

import pytest
from langchain_core.messages import AIMessage
from rich.console import Console

from cadenza import cli, prompts
from cadenza.context import Context, parse_now


@pytest.mark.parametrize(
    ("model", "env", "expected"),
    [
        ("anthropic/claude-haiku-5-5", {}, "copy .env.example to .env"),
        ("anthropic/claude-haiku-5-5", {"ANTHROPIC_API_KEY": "x"}, None),
        ("claude-haiku-5-5", {"ANTHROPIC_API_KEY": "x"}, "provider/model"),
        ("ollama/llama3", {}, None),
    ],
)
def test_config_error_explains_what_is_missing(monkeypatch, model, env, expected):
    monkeypatch.setattr(cli, "load_chat_model", lambda name: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    error = cli.config_error(model)
    assert error is None if expected is None else expected in error


def test_missing_provider_package_says_which_extra_to_install(monkeypatch):
    def missing(name):
        raise ImportError(
            "Initializing ChatOllama requires the langchain-ollama package."
        )

    monkeypatch.setattr(cli, "load_chat_model", missing)
    assert cli.config_error("ollama/qwen3:8b") == (
        "The package for provider 'ollama' is not installed: uv sync --extra ollama."
    )


def test_unknown_provider_is_reported_without_a_traceback(monkeypatch):
    def unsupported(name):
        raise ValueError("Unsupported model_provider='nope'.")

    monkeypatch.setattr(cli, "load_chat_model", unsupported)
    assert cli.config_error("nope/model").startswith("Cannot use MODEL=nope/model")


def test_missing_key_exits_with_one_clear_line(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda path: None)
    monkeypatch.setenv("MODEL", "anthropic/claude-haiku-5-5")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 1
    assert capsys.readouterr().err.strip() == (
        "ANTHROPIC_API_KEY is not set: copy .env.example to .env and set your key."
    )


def run_chat(monkeypatch, lines):
    """Drive the chat loop with scripted input; return the output and the turns sent."""
    sent = []

    def fake_turn(text, context, thread_id):
        sent.append((text, thread_id))
        return [AIMessage(f"resposta para {text}")]

    feed = iter(lines)

    def fake_input(prompt):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(cli, "run_turn", fake_turn)
    console = Console(file=io.StringIO(), width=200)
    monkeypatch.setattr(console, "input", fake_input)
    cli.chat(console, Context(now=parse_now("2026-02-20T10:00")))
    return console.file.getvalue(), sent


def test_chat_greets_answers_and_says_goodbye(monkeypatch):
    output, sent = run_chat(monkeypatch, ["Quanto custa o [Takamine]?", "/sair"])
    assert prompts.GREETING in output
    assert "resposta para Quanto custa o [Takamine]?" in output
    assert prompts.GOODBYE in output
    assert [text for text, _ in sent] == ["Quanto custa o [Takamine]?"]


def test_long_messages_are_refused_before_reaching_the_model(monkeypatch):
    output, sent = run_chat(monkeypatch, ["x" * (cli.MAX_MESSAGE_CHARS + 1), "/sair"])
    assert prompts.MESSAGE_TOO_LONG in output
    assert sent == []


def test_new_command_starts_a_separate_conversation(monkeypatch):
    _, sent = run_chat(monkeypatch, ["oi", "/new", "oi de novo", "/sair"])
    assert sent[0][1] != sent[1][1]


def test_end_of_input_closes_the_chat_without_a_traceback(monkeypatch):
    output, _ = run_chat(monkeypatch, [])
    assert prompts.GOODBYE in output


def test_only_the_label_of_a_reply_is_styled(monkeypatch):
    printed = []
    console = Console(file=io.StringIO())
    monkeypatch.setattr(
        console, "print", lambda renderable, **kw: printed.append(renderable)
    )
    cli.say(console, "Olá [cliente]")
    (text,) = printed
    assert text.plain == "CaduAI: Olá [cliente]"
    assert not text.style
    assert [(span.start, span.end) for span in text.spans] == [(0, len("CaduAI: "))]
