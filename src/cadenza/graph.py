"""ReAct agent: the model picks tools and writes the reply; the tools compute the facts."""

from __future__ import annotations

from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from cadenza import prompts
from cadenza.context import Context
from cadenza.state import InputState, State
from cadenza.tools import TOOLS
from cadenza.utils import load_chat_model

# Each tool round costs two steps (model + tools), so this allows about five rounds per turn.
MAX_GRAPH_STEPS = 12


def call_model(state: State, runtime: Runtime[Context]) -> dict[str, list[AIMessage]]:
    """Ask the model for the next step: a tool call or the reply to the customer."""
    model = load_chat_model(runtime.context.model).bind_tools(TOOLS)
    # Same prompt on every call of a session (fixed `now`), so thinking blocks stay valid.
    system = prompts.build_system_prompt(runtime.context.now)
    response = cast(
        AIMessage,
        model.invoke([{"role": "system", "content": system}, *state["messages"]]),
    )
    if state.get("is_last_step") and response.tool_calls:
        # Replace instead of raising, so no tool call is left without a result in the history.
        return {
            "messages": [AIMessage(id=response.id, content=prompts.STEP_LIMIT_REPLY)]
        }
    return {"messages": [response]}


def route_model_output(state: State) -> Literal["__end__", "tools"]:
    """Run tools while the model asks for them; otherwise end the turn."""
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else "__end__"


builder = StateGraph(State, input_schema=InputState, context_schema=Context)
builder.add_node(call_model)
builder.add_node("tools", ToolNode(TOOLS, handle_tool_errors=True))
builder.add_edge("__start__", "call_model")
builder.add_conditional_edges("call_model", route_model_output)
builder.add_edge("tools", "call_model")
# ponytail: history lives in RAM per thread_id; swap in SqliteSaver to keep it across runs.
graph = builder.compile(checkpointer=MemorySaver(), name="Cadenza")


def run_turn(
    text: str, context: Context, thread_id: str, max_steps: int = MAX_GRAPH_STEPS
) -> list[BaseMessage]:
    """Send one customer message and return the messages this turn added."""
    config: Any = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": max_steps,
    }
    before = len(graph.get_state(config).values.get("messages", []))
    result = graph.invoke(
        {"messages": [("user", text)]}, config=config, context=context
    )
    return result["messages"][before:]
