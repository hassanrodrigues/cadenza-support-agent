import itertools
import uuid

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from cadenza import graph
from cadenza.context import Context, parse_now
from cadenza.utils import get_message_text

NOW = parse_now("2026-02-20T10:00")


class FakeToolModel(GenericFakeChatModel):
    """Scripted model: replays the given messages and accepts bind_tools."""

    def bind_tools(self, tools, **kwargs):
        return self


def tool_call(name, **args):
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": uuid.uuid4().hex}]
    )


@pytest.fixture
def script(monkeypatch):
    def use(replies):
        model = FakeToolModel(messages=iter(replies))
        monkeypatch.setattr(graph, "load_chat_model", lambda name: model)

    return use


def new_thread():
    return uuid.uuid4().hex


def test_turn_runs_the_tool_and_returns_the_model_reply(script):
    script(
        [
            tool_call("get_product_details", name_or_id="Takamine GD20"),
            AIMessage("Custa R$ 2.199,00."),
        ]
    )
    added = graph.run_turn(
        "Quanto custa o Takamine GD20?", Context(now=NOW), new_thread()
    )
    tool_result = next(m for m in added if isinstance(m, ToolMessage))
    assert "R$ 2.199,00" in tool_result.content
    assert get_message_text(added[-1]) == "Custa R$ 2.199,00."


def test_tools_receive_the_session_reference_time(script):
    script(
        [tool_call("lookup_orders", contact="leticia.rocha@jmail.com"), AIMessage("ok")]
    )
    added = graph.run_turn("meu pedido", Context(now=NOW), new_thread())
    tool_result = next(m for m in added if isinstance(m, ToolMessage))
    assert '"days_since_delivery": 3' in tool_result.content


def test_history_is_kept_per_thread_and_a_new_thread_starts_empty(script):
    script([AIMessage("Oi!"), AIMessage("Claro."), AIMessage("Olá de novo.")])
    thread, context = new_thread(), Context(now=NOW)
    graph.run_turn("oi", context, thread)
    graph.run_turn("e agora?", context, thread)
    history = graph.graph.get_state({"configurable": {"thread_id": thread}}).values[
        "messages"
    ]
    assert [type(m) for m in history] == [
        HumanMessage,
        AIMessage,
        HumanMessage,
        AIMessage,
    ]
    added = graph.run_turn("oi", context, new_thread())
    assert len(added) == 2


def test_step_limit_ends_the_turn_with_a_friendly_reply_and_no_dangling_tool_call(
    script,
):
    script(tool_call("list_active_promotions") for _ in itertools.count())
    thread = new_thread()
    added = graph.run_turn("promoções?", Context(now=NOW), thread, max_steps=4)
    assert get_message_text(added[-1]) == graph.prompts.STEP_LIMIT_REPLY
    assert not added[-1].tool_calls
    calls = sum(len(m.tool_calls) for m in added if isinstance(m, AIMessage))
    assert calls == sum(isinstance(m, ToolMessage) for m in added)


def test_every_tool_converts_to_a_provider_schema_without_the_runtime_argument():
    from langchain_anthropic.chat_models import convert_to_anthropic_tool

    schemas = {t.name: convert_to_anthropic_tool(t) for t in graph.TOOLS}
    assert len(schemas) == 6
    for schema in schemas.values():
        assert "runtime" not in schema["input_schema"]["properties"]
        assert schema["description"]
    assert set(schemas["lookup_orders"]["input_schema"]["properties"]) == {
        "contact",
        "order_id",
    }
