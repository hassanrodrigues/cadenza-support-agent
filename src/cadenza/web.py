"""Optional browser chat with CaduAI, on the same agent as the CLI.

Usage: uv run --extra ui streamlit run src/cadenza/web.py   (needs the provider key)
"""

from __future__ import annotations

import uuid

import streamlit as st
from dotenv import load_dotenv

from cadenza import graph, prompts
from cadenza.cli import config_error
from cadenza.context import ROOT_DIR, Context
from cadenza.utils import get_message_text


def show(role: str, text: str) -> None:
    # Escape "$" so "R$ 10 ... R$ 20" is not rendered as a LaTeX formula.
    st.chat_message(role).markdown(text.replace("$", r"\$"))


load_dotenv(ROOT_DIR / ".env")
st.set_page_config(page_title="CaduAI · Empório da Música")
st.title("CaduAI · Empório da Música")

if "thread_id" not in st.session_state:
    try:
        context = Context()
    except ValueError:
        st.error("EMPORIO_NOW must look like 2026-02-20T10:00.")
        st.stop()
    if error := config_error(context.model):
        st.error(error)
        st.stop()
    st.session_state.context = context
    st.session_state.thread_id = uuid.uuid4().hex
    st.session_state.history = [("assistant", prompts.GREETING)]

with st.sidebar:
    st.caption(f"Model: {st.session_state.context.model}")
    st.caption(f"Store clock: {st.session_state.context.now:%d/%m/%Y %H:%M}")
    if st.button(prompts.NEW_CONVERSATION):
        st.session_state.clear()
        st.rerun()

for role, text in st.session_state.history:
    show(role, text)

if text := st.chat_input(prompts.WEB_INPUT_PLACEHOLDER):
    show("user", text)
    with st.spinner(prompts.TYPING):
        added = graph.run_turn(
            text, st.session_state.context, st.session_state.thread_id
        )
    reply = get_message_text(added[-1])
    show("assistant", reply)
    st.session_state.history += [("user", text), ("assistant", reply)]
