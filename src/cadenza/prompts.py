"""System prompt and every fixed message the customer can see."""

from __future__ import annotations

from datetime import datetime

from cadenza.policies import OFFICIAL_WHATSAPP

SYSTEM_PROMPT = """You are CaduAI, the virtual assistant of Empório da Música, a musical instrument \
store in Campo Grande, MS, Brazil. Always reply to the customer in Brazilian Portuguese.

<current_context>
{current_context}
</current_context>"""

STEP_LIMIT_REPLY = (
    "Essa ficou difícil de resolver por aqui. Pode perguntar de outro jeito? "
    f"Se preferir, a nossa equipe atende no WhatsApp {OFFICIAL_WHATSAPP}."
)


def build_system_prompt(now: datetime) -> str:
    """System prompt for a session; `now` is fixed per session, so the prompt never changes."""
    return SYSTEM_PROMPT.format(
        current_context=f"Now: {now:%A, %d/%m/%Y %H:%M} (America/Campo_Grande)."
    )
