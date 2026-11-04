"""Support tools: order lookup with contact verification, store policies and tickets."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from functools import cache
from typing import Any, Literal

from langchain.tools import ToolRuntime

from cadenza import order_rules, policies, prompts
from cadenza import store_data as sd
from cadenza.context import DATA_DIR, RUNTIME_DIR, Context
from cadenza.tools.catalog import cached_store

logger = logging.getLogger(__name__)

PolicyTopic = Literal[
    "sobre_a_loja",
    "horario",
    "pagamento",
    "trocas_devolucoes",
    "frete_entregas",
    "promocoes",
    "garantia",
    "privacidade",
]
TicketKind = Literal["complaint", "human_agent"]

# Same answer for "no such contact" and "not your order", so nothing leaks.
ORDER_NOT_FOUND = (
    "No order found for this contact. Do not say whether the order exists; ask the customer "
    "to check the e-mail or phone used in the purchase."
)
MAX_TICKET_SUMMARY = 500
MAX_TICKET_CONTACT = 120
TICKETS_PATH = RUNTIME_DIR / "tickets.jsonl"


@cache
def _manual() -> list[policies.Section]:
    return policies.load_manual(DATA_DIR / "store_policies.pdf")


def _br_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _payment_label(method: str) -> str:
    if method.startswith("credit_"):
        return prompts.CREDIT_CARD_LABEL.format(
            installments=method.removeprefix("credit_")
        )
    return prompts.PAYMENT_LABELS.get(method, method)


def _order_view(order: dict[str, Any], today: date) -> dict[str, Any]:
    store = cached_store()
    items = store.order_items[store.order_items["order_id"] == order["order_id"]]
    names = store.products["name"]
    view: dict[str, Any] = {
        "order_id": order["order_id"],
        "order_date": _br_date(order["order_date"]),
        "status": prompts.ORDER_STATUS_LABELS[order["status"]],
        "items": [
            f"{qty}x {names[pid]}"
            for qty, pid in zip(items["quantity"], items["product_id"])
        ],
        "total": sd.format_brl(sd.to_money(order["total_brl"])),
        "payment": _payment_label(order["payment_method"]),
        "days_since_order": (today - order["order_date"]).days,
    }
    eta = order["estimated_delivery"]
    if isinstance(order["tracking_code"], str):
        view["tracking_code"] = order["tracking_code"]
    if eta:
        view["estimated_delivery"] = _br_date(eta)
    if order["status"] == "shipped" and eta < today:
        view["delivery_overdue"] = True
    if order["status"] == "delivered":
        view["days_since_delivery"] = (today - eta).days
        windows = order_rules.return_windows(order["order_date"], eta, today)
        view["returns"] = {
            rule: {"eligible": w.eligible, "deadline": _br_date(w.deadline)}
            for rule, w in windows.items()
        }
    return view


def lookup_orders(
    contact: str, order_id: int | None = None, *, runtime: ToolRuntime[Context]
) -> dict[str, Any]:
    """Look up the customer's orders: status, items, total, payment, tracking and, for delivered
    orders, return, exchange and warranty eligibility with deadlines already computed (delivery
    date = estimated delivery). Requires the e-mail or the full phone number with area code (DDD)
    given by the customer in this conversation. order_id narrows the result to one order.
    """
    store = cached_store()
    today = runtime.context.now.date()
    customer_ids = order_rules.find_customer_ids(store.customers, contact)
    if customer_ids is None:
        return {
            "error": "Ask for the e-mail or the full phone number with area code (DDD)."
        }
    if len(customer_ids) > 1 and order_id is None:
        return {
            "error": "This e-mail matches more than one customer. Ask for the phone number or the order number."
        }
    orders = store.orders[store.orders["customer_id"].isin(customer_ids)]
    orders = orders[orders["order_date"].map(lambda day: day <= today)]
    if order_id is not None:
        orders = orders[orders["order_id"] == order_id]
    if orders.empty:
        return {"error": ORDER_NOT_FOUND}
    return {"orders": [_order_view(o, today) for o in orders.to_dict("records")]}


def get_store_policy(topic: PolicyTopic) -> dict[str, Any]:
    """Read the store manual on one topic: sobre_a_loja (address, contacts, company data),
    horario (opening hours), pagamento (payment methods, installment rules), trocas_devolucoes
    (returns and exchanges), frete_entregas (shipping), promocoes (promotion rules), garantia
    (warranty), privacidade (personal data, LGPD).
    """
    result = {"topic": topic, "text": policies.topic_text(_manual(), topic)}
    if topic in policies.TOPIC_NOTES:
        result["note"] = policies.TOPIC_NOTES[topic]
    return result


def open_support_ticket(
    kind: TicketKind,
    summary: str,
    contact: str,
    order_id: int | None = None,
    *,
    runtime: ToolRuntime[Context],
) -> dict[str, Any]:
    """Open a ticket for a complaint or a request to talk to a person. Collect a short summary
    and the customer's e-mail or phone first. Returns the protocol number and the response time.
    """
    summary, contact = (
        summary.strip()[:MAX_TICKET_SUMMARY],
        contact.strip()[:MAX_TICKET_CONTACT],
    )
    if not summary:
        return {"error": "Ask for a short summary of the issue first."}
    if not order_rules.is_valid_contact(contact):
        return {
            "error": "Ask for a valid e-mail or the full phone number with area code (DDD)."
        }
    now = runtime.context.now
    protocol = f"EM-{now:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "protocol": protocol,
        "created_at": now.isoformat(),
        "kind": kind,
        "summary": summary,
        "contact": contact,
        "order_id": order_id,
    }
    TICKETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TICKETS_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Support ticket %s opened (%s)", protocol, kind)
    return {"protocol": protocol, "response_time": prompts.TICKET_RESPONSE_TIME}
