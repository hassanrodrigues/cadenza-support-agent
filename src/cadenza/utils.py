"""Model loading and message helpers."""

from __future__ import annotations

from functools import cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

# Adaptive thinking on Claude Haiku 5.5 counts toward max_tokens, so leave room for it.
MAX_TOKENS = 8192
MAX_RETRIES = 3  # the provider client retries with exponential backoff


@cache
def load_chat_model(fully_specified_name: str) -> BaseChatModel:
    """Load a chat model from 'provider/model', e.g. 'anthropic/claude-haiku-5-5'."""
    provider, _, model = fully_specified_name.partition("/")
    if not provider or not model:
        raise ValueError(
            f"MODEL must look like provider/model, got {fully_specified_name!r}"
        )
    # No temperature, top_p or top_k: the Haiku 5.5 migration guide says not to send them.
    return init_chat_model(
        model, model_provider=provider, max_tokens=MAX_TOKENS, max_retries=MAX_RETRIES
    )


def get_message_text(message: BaseMessage) -> str:
    """Text blocks of a message; thinking and tool-use blocks are skipped."""
    return message.text.strip()
