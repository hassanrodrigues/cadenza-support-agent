"""Optional browser chat with CaduAI, on the same agent as the CLI.

Usage: uv run --extra ui streamlit run src/cadenza/web.py   (needs the provider key)
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv

from cadenza import graph, prompts
from cadenza.cli import config_error
from cadenza.context import ROOT_DIR, STORE_TZ, Context, parse_now
from cadenza.policies import next_opening
from cadenza.utils import get_message_text

AVATARS = {"assistant": "🎸", "user": "🙂"}
# Without EMPORIO_NOW the page starts inside the dataset (Oct 2025 to Mar 2026), so order
# deadlines look as a customer would have seen them.
DEMO_NOW = "2026-02-20T10:00"


def show(role: str, text: str, details: tuple | None = None) -> None:
    message = st.chat_message(role, avatar=AVATARS[role])
    # Escape "$" so "R$ 10 ... R$ 20" is not rendered as a LaTeX formula.
    message.markdown(text.replace("$", r"\$"))
    if details:
        calls, (tokens_in, tokens_out) = details
        with message.expander("Tools called"):
            st.code("\n".join(calls) or "none", language=None)
            st.caption(
                f"Tokens: {tokens_in:,} in, {tokens_out:,} out (output includes thinking)"
            )


def start(context: Context) -> None:
    """New conversation: fresh thread and history, with this context's fixed `now`."""
    st.session_state.context = context
    st.session_state.thread_id = uuid.uuid4().hex
    st.session_state.history = [("assistant", prompts.GREETING, None)]


load_dotenv(ROOT_DIR / ".env")
st.set_page_config(page_title="CaduAI · Empório da Música", page_icon="🎸")
st.title("🎸 CaduAI")
st.caption(prompts.WEB_SUBTITLE)

if "thread_id" not in st.session_state:
    try:
        context = Context()
    except ValueError:
        st.error("EMPORIO_NOW must look like 2026-02-20T10:00.")
        st.stop()
    if error := config_error(context.model):
        st.error(error)
        st.stop()
    now = context.now if os.environ.get("EMPORIO_NOW") else parse_now(DEMO_NOW)
    start(Context(model=context.model, now=now.replace(second=0, microsecond=0)))

context = st.session_state.context
with st.sidebar:
    st.subheader("Empório da Música")
    st.caption(f"Model: {context.model}")
    day = st.date_input("Store date", context.now.date(), format="DD/MM/YYYY")
    hour = st.time_input(
        "Store time",
        context.now.time().replace(tzinfo=None),
        step=timedelta(minutes=30),
    )
    picked = datetime.combine(day, hour, tzinfo=STORE_TZ)
    if picked != context.now:
        # `now` is fixed per conversation, so a new time starts a new one.
        start(Context(model=context.model, now=picked))
        st.rerun()
    opening = next_opening(context.now)
    if opening == context.now:
        st.success("Store open now")
    else:
        st.info(f"Store closed; the team is back {opening:%a %d/%m at %H:%M}")
    if st.button(prompts.NEW_CONVERSATION, width="stretch"):
        start(context)
        st.rerun()

for role, text, details in st.session_state.history:
    show(role, text, details)

text = st.chat_input(prompts.WEB_INPUT_PLACEHOLDER)
if len(st.session_state.history) == 1:
    # Starter questions until the first message; a click sends it like typed text.
    for column, (i, suggestion) in zip(
        st.columns(len(prompts.WEB_SUGGESTIONS)), enumerate(prompts.WEB_SUGGESTIONS)
    ):
        label = suggestion.replace("$", r"\$")
        if column.button(label, key=f"suggestion-{i}", width="stretch"):
            text = suggestion

if text:
    show("user", text)
    with st.spinner(prompts.TYPING):
        added = graph.run_turn(text, context, st.session_state.thread_id)
    details = (graph.tool_calls(added), graph.token_usage(added))
    reply = get_message_text(added[-1])
    st.session_state.history += [("user", text, None), ("assistant", reply, details)]
    st.rerun()
