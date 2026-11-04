import json
import re
from typing import get_args

from cadenza import policies, tools
from cadenza.tools import support


def test_orders_are_found_by_phone_in_any_format(at):
    for phone in ("(67) 99812-3456", "67998123456", "+55 67 99812-3456"):
        result = support.lookup_orders(phone, runtime=at("2026-03-25T10:00"))
        assert [o["order_id"] for o in result["orders"]] == [4]


def test_partial_phone_is_refused(at):
    result = support.lookup_orders("99812-3456", runtime=at("2026-03-25T10:00"))
    assert "DDD" in result["error"]


def test_unknown_contact_and_someone_elses_order_get_the_same_answer(at):
    now = at("2026-03-25T10:00")
    unknown = support.lookup_orders("nobody@jmail.com", runtime=now)
    not_theirs = support.lookup_orders(
        "lucas.mendes@jmail.com", order_id=7, runtime=now
    )
    assert unknown == not_theirs == {"error": support.ORDER_NOT_FOUND}


def test_contact_without_orders_and_an_order_number_gets_the_same_answer(at):
    # Customer 43 has no orders; an empty frame used to crash the order_id filter.
    result = support.lookup_orders(
        "(67) 99456-3456", order_id=10, runtime=at("2026-03-25T10:00")
    )
    assert result == {"error": support.ORDER_NOT_FOUND}


def test_shared_email_asks_for_more_unless_order_number_is_given(at):
    now = at("2026-03-25T10:00")
    assert (
        "more than one"
        in support.lookup_orders("bruno.martins@jmail.com", runtime=now)["error"]
    )
    result = support.lookup_orders("bruno.martins@jmail.com", order_id=10, runtime=now)
    assert result["orders"][0]["total"] == "R$ 8.732,00"


def test_delivered_order_comes_with_return_eligibility_computed(at):
    result = support.lookup_orders(
        "leticia.rocha@jmail.com", runtime=at("2026-02-20T10:00")
    )
    order = result["orders"][0]
    assert order["order_id"] == 7
    assert order["status"] == "entregue"
    assert order["payment"] == "cartão de crédito em 3x"
    assert order["days_since_delivery"] == 3
    assert order["returns"]["regret_return"] == {
        "eligible": True,
        "deadline": "24/02/2026",
    }
    later = support.lookup_orders(
        "leticia.rocha@jmail.com", runtime=at("2026-03-01T10:00")
    )
    assert later["orders"][0]["returns"]["regret_return"]["eligible"] is False


def test_shipped_order_past_its_estimate_is_flagged_overdue(at):
    result = support.lookup_orders("(67) 99654-7821", runtime=at("2026-03-10T10:00"))
    order = result["orders"][0]
    assert order["status"] == "enviado"
    assert order["tracking_code"] == "BRJL5544332BR"
    assert order["delivery_overdue"] is True
    assert "returns" not in order


def test_orders_after_the_reference_time_are_ignored(at):
    result = support.lookup_orders(
        "camila.duarte@inlook.com", runtime=at("2026-03-01T10:00")
    )
    assert result == {"error": support.ORDER_NOT_FOUND}


def test_order_lookup_result_is_plain_json(at):
    json.dumps(
        support.lookup_orders("leticia.rocha@jmail.com", runtime=at("2026-02-20T10:00"))
    )


def test_tool_schemas_hide_the_injected_runtime():
    from langgraph.prebuilt import ToolNode

    node = ToolNode(tools.TOOLS, handle_tool_errors=True)
    schema = node.tools_by_name["lookup_orders"].tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"contact", "order_id"}


def test_policy_topics_match_the_manual_mapping():
    assert set(get_args(support.PolicyTopic)) == set(policies.TOPIC_SECTIONS)


def test_policy_lookup_returns_manual_text_and_resolution_note():
    assert "09:00 às 18:00" in support.get_store_policy("horario")["text"]
    payment = support.get_store_policy("pagamento")
    assert "3.1 Regras de Parcelamento" in payment["text"]
    assert "prevails" in payment["note"]


def test_ticket_is_saved_with_bounded_fields_and_returns_a_protocol(
    tmp_path, monkeypatch, at
):
    path = tmp_path / "tickets.jsonl"
    monkeypatch.setattr(support, "TICKETS_PATH", path)
    result = support.open_support_ticket(
        "complaint",
        "x" * 2000,
        "leticia.rocha@jmail.com",
        order_id=7,
        runtime=at("2026-02-20T10:00"),
    )
    assert re.fullmatch(r"EM-20260220-[0-9A-F]{6}", result["protocol"])
    assert result["response_time"] == "até 24 horas úteis"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["protocol"] == result["protocol"]
    assert len(saved["summary"]) == support.MAX_TICKET_SUMMARY
    assert saved["order_id"] == 7


def test_ticket_without_contact_is_not_opened(tmp_path, monkeypatch, at):
    path = tmp_path / "tickets.jsonl"
    monkeypatch.setattr(support, "TICKETS_PATH", path)
    result = support.open_support_ticket(
        "human_agent",
        "quero falar com alguém",
        "  ",
        runtime=at("2026-02-20T10:00"),
    )
    assert "error" in result
    assert not path.exists()


def test_ticket_needs_a_valid_contact(tmp_path, monkeypatch, at):
    path = tmp_path / "tickets.jsonl"
    monkeypatch.setattr(support, "TICKETS_PATH", path)
    refused = support.open_support_ticket(
        "complaint", "produto chegou riscado", "abc", runtime=at("2026-02-20T10:00")
    )
    assert "DDD" in refused["error"]
    assert not path.exists()
    opened = support.open_support_ticket(
        "complaint",
        "produto chegou riscado",
        "(67) 99789-0123",
        runtime=at("2026-02-20T10:00"),
    )
    assert opened["protocol"].startswith("EM-20260220-")
