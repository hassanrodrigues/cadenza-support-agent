"""Terminal chat with CaduAI: one session per run, /new starts another, /sair exits."""

from __future__ import annotations

import logging
import os
import sys
import uuid

from dotenv import load_dotenv
from rich.console import Console
from rich.text import Text

from cadenza import prompts
from cadenza.context import ROOT_DIR, RUNTIME_DIR, Context
from cadenza.graph import run_turn
from cadenza.utils import get_message_text, load_chat_model

MAX_MESSAGE_CHARS = 2000
EXIT_COMMANDS = {"/sair", "/exit", "/quit"}
# Keys we can check before the first call; Ollama and Bedrock authenticate differently.
PROVIDER_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
# pyproject extra that installs each provider's LangChain package.
PROVIDER_EXTRAS = {
    "openai": "openai",
    "google_genai": "google",
    "groq": "groq",
    "openrouter": "openrouter",
    "bedrock_converse": "aws",
    "ollama": "ollama",
}


def config_error(model: str) -> str | None:
    """Why the agent cannot start with this MODEL and environment, if anything."""
    provider, _, name = model.partition("/")
    if not provider or not name:
        return f"MODEL must look like provider/model, got {model!r}. See .env.example."
    key = PROVIDER_KEYS.get(provider)
    if key and not os.environ.get(key):
        return f"{key} is not set: copy .env.example to .env and set your key."
    try:
        load_chat_model(model)  # builds the client only; no request is sent
    except ImportError:
        extra = PROVIDER_EXTRAS.get(provider)
        hint = f"uv sync --extra {extra}" if extra else "install its LangChain package"
        return f"The package for provider '{provider}' is not installed: {hint}."
    except ValueError as error:
        return f"Cannot use MODEL={model}: {error}"
    return None


def _say(console: Console, text: str) -> None:
    # Text() keeps the model's brackets and asterisks from being read as rich markup.
    console.print(Text("CaduAI: ", style="bold magenta") + Text(text))


def chat(console: Console, context: Context) -> None:
    """Read customer messages until /sair, keeping the history of the current session."""
    thread_id = uuid.uuid4().hex
    console.print(Text(prompts.CLI_HELP, style="dim"))
    _say(console, prompts.GREETING)
    while True:
        try:
            text = console.input("[bold cyan]Você:[/] ").strip()
            if not text:
                continue
            if text.lower() in EXIT_COMMANDS:
                break
            if text.lower() == "/new":
                context, thread_id = Context(), uuid.uuid4().hex
                console.rule(prompts.NEW_CONVERSATION)
                _say(console, prompts.GREETING)
                continue
            if len(text) > MAX_MESSAGE_CHARS:
                _say(console, prompts.MESSAGE_TOO_LONG)
                continue
            with console.status("CaduAI está digitando..."):
                added = run_turn(text, context, thread_id)
            _say(console, get_message_text(added[-1]))
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
    _say(console, prompts.GOODBYE)


def main() -> None:
    """Entry point of the `cadenza` command."""
    load_dotenv(ROOT_DIR / ".env")
    context = Context()
    error = config_error(context.model)
    if error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
    RUNTIME_DIR.mkdir(exist_ok=True)
    # Logs go to a file so the customer never sees a stack trace; no personal data is logged.
    logging.basicConfig(
        filename=RUNTIME_DIR / "cadenza.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    chat(Console(), context)


if __name__ == "__main__":
    main()
