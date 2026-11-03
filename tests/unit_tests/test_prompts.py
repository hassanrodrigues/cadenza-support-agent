import re

from cadenza import prompts
from cadenza.context import parse_now
from cadenza.policies import OFFICIAL_EMAIL, OFFICIAL_WHATSAPP

TUESDAY_MORNING = parse_now("2026-11-03T10:00")


def test_prompt_is_identical_for_the_same_session_time():
    assert prompts.build_system_prompt(TUESDAY_MORNING) == prompts.build_system_prompt(
        parse_now("2026-11-03T10:00")
    )


def test_prompt_has_every_section_in_order():
    prompt = prompts.build_system_prompt(TUESDAY_MORNING)
    tags = re.findall(r"^<(\w+)>$", prompt, flags=re.M)
    assert tags == [
        "persona",
        "store_rules",
        "when_to_use_tools",
        "response_format",
        "current_context",
    ]


def test_prompt_sets_language_persona_and_official_contacts():
    prompt = prompts.build_system_prompt(TUESDAY_MORNING)
    assert "Always reply to the customer in Brazilian Portuguese" in prompt
    assert prompts.GREETING in prompt
    assert prompts.GREETING.startswith("Oi! Eu sou o CaduAI, o assistente virtual")
    assert OFFICIAL_WHATSAPP in prompt
    assert OFFICIAL_EMAIL in prompt
    assert "{" not in prompt


def test_current_context_says_the_store_is_open_during_business_hours():
    context = prompts.current_context(TUESDAY_MORNING)
    assert context.startswith("Now: Tuesday, 03/11/2026 at 10:00")
    assert "open now" in context


def test_current_context_says_when_the_team_is_back_after_hours():
    context = prompts.current_context(parse_now("2026-11-07T14:00"))
    assert "closed now; the team is back on Monday, 09/11/2026 at 09:00" in context
