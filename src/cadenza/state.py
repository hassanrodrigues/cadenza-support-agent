"""Graph state: the message history plus LangGraph's last-step flag."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep

# TypedDict rather than the template's dataclasses: tools get the state through ToolRuntime,
# which expects a dict.


class InputState(TypedDict):
    """What callers send: new messages, appended to the history (never edited)."""

    messages: Annotated[list[AnyMessage], add_messages]


class State(InputState):
    """Full state; is_last_step turns true one step before the recursion limit."""

    is_last_step: IsLastStep
