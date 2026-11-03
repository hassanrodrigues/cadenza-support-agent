import pytest
from langchain_core.messages import AIMessage

from cadenza import utils


def test_model_name_is_split_into_provider_and_model_without_sampling_params(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        utils, "init_chat_model", lambda *a, **kw: calls.append((a, kw))
    )
    utils.load_chat_model.cache_clear()
    utils.load_chat_model("anthropic/claude-haiku-5-5")
    utils.load_chat_model.cache_clear()
    ((args, kwargs),) = calls
    assert args == ("claude-haiku-5-5",)
    assert kwargs["model_provider"] == "anthropic"
    assert kwargs["max_tokens"] >= 4096
    assert not {"temperature", "top_p", "top_k"} & set(kwargs)


def test_model_ids_with_slashes_keep_everything_after_the_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(utils, "init_chat_model", lambda *a, **kw: calls.append(a))
    utils.load_chat_model.cache_clear()
    utils.load_chat_model("openrouter/anthropic/claude-haiku-5-5")
    utils.load_chat_model.cache_clear()
    assert calls == [("anthropic/claude-haiku-5-5",)]


@pytest.mark.parametrize("name", ["claude-haiku-5-5", "anthropic/", "/claude"])
def test_model_name_without_provider_is_rejected(name):
    with pytest.raises(ValueError, match="provider/model"):
        utils.load_chat_model(name)


def test_message_text_skips_thinking_blocks():
    message = AIMessage(
        content=[
            {"type": "thinking", "thinking": "internal", "signature": "x"},
            {"type": "text", "text": " Olá! "},
        ]
    )
    assert utils.get_message_text(message) == "Olá!"
