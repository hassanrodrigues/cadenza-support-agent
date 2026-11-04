import json
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage

from cadenza import prompts
from cadenza.context import ROOT_DIR
from evals import run_evals


@pytest.mark.parametrize(
    "text", ["R$2199", "R$ 2.199,00", "2199 reais", "sai por r$ 2.199 no cartão"]
)
def test_money_formats_are_normalized_before_comparing(text):
    assert Decimal("2199.00") in run_evals.money_values(text)


def test_cents_and_several_amounts_are_all_found():
    values = run_evals.money_values(
        "De R$ 5.999,00 por R$ 5.519,08, ou 12x de R$ 459,92."
    )
    assert values == {Decimal("5999.00"), Decimal("5519.08"), Decimal("459.92")}


def test_facts_match_text_without_accents_money_or_any_of_a_list():
    reply = "A promoção já terminou. Hoje ele está por R$ 2.199,00."
    assert run_evals.matches("promocao ja terminou", reply)
    assert run_evals.matches({"money": "2199.00"}, reply)
    assert run_evals.matches(["encerrou", "terminou"], reply)
    assert not run_evals.matches({"money": "1935.12"}, reply)


def test_check_reports_missing_tool_missing_fact_and_forbidden_text():
    case = {
        "expected_tools": ["lookup_orders"],
        "expected_facts": ["24/02"],
        "forbidden": ["98543-2109"],
    }
    failures = run_evals.check(
        case, ["telefone 98543-2109"], ['search_products(query="x")']
    )
    assert failures == [
        "expected a call to lookup_orders",
        'missing "24/02"',
        'forbidden "98543-2109"',
    ]


def test_case_file_has_ten_functional_and_seven_adversarial_cases():
    cases = json.loads((ROOT_DIR / "evals" / "cases.json").read_text(encoding="utf-8"))
    suites = [c["suite"] for c in cases]
    assert suites.count("functional") == 10
    assert suites.count("adversarial") == 7
    assert len({c["id"] for c in cases}) == len(cases)
    assert all(c["turns"] and c["now"] for c in cases)


def test_failed_model_call_aborts_the_run(monkeypatch):
    def failed_turn(text, context, thread):
        return [AIMessage(prompts.API_ERROR_REPLY)]

    monkeypatch.setattr(run_evals, "run_turn", failed_turn)
    case = {"id": "F01", "now": "2026-02-20T10:00", "turns": ["oi"]}
    with pytest.raises(SystemExit, match="F01: model call failed"):
        run_evals.run_case(case)
