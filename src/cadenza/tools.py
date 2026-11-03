"""Tools exposed to the LLM. Each docstring is part of the prompt."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from decimal import Decimal
from functools import cache
from typing import Any, Literal

import pandas as pd
from langchain.tools import ToolRuntime
from rapidfuzz import fuzz

from cadenza import policies
from cadenza import store_data as sd
from cadenza.context import DATA_DIR, RUNTIME_DIR, Context

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

MAX_SEARCH_RESULTS = 8
MAX_ALTERNATIVES = 3
MAX_CANDIDATES = 5
FUZZY_MIN_SCORE = 80
FUZZY_AMBIGUITY_MARGIN = 5
ORDER_STATUS = {
    "pending": "pendente",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}
PAYMENT_METHODS = {
    "pix": "PIX",
    "debit": "cartão de débito",
    "boleto": "boleto bancário",
}
# Same answer for "no such contact" and "not your order", so nothing leaks.
ORDER_NOT_FOUND = (
    "No order found for this contact. Do not say whether the order exists; ask the customer "
    "to check the e-mail or phone used in the purchase."
)
MAX_TICKET_SUMMARY = 500
MAX_TICKET_CONTACT = 120
TICKETS_PATH = RUNTIME_DIR / "tickets.jsonl"
TICKET_RESPONSE_TIME = "até 24 horas úteis"
STOPWORDS = set("a o as os de da do das dos e em com para um uma".split())


@cache
def _store() -> sd.Store:
    return sd.load_store(DATA_DIR)


@cache
def _manual() -> list[policies.Section]:
    return policies.load_manual(DATA_DIR / "store_policies.pdf")


def _price_fields(p: dict[str, Any]) -> dict[str, str]:
    fields = {"price": sd.format_brl(p["effective_price"])}
    if p["promo_percent"]:
        fields["original_price"] = sd.format_brl(p["price"])
        fields["discount"] = (
            f"{p['promo_percent']}% off ({p['promo_name']}); PIX discount does not stack"
        )
    else:
        fields["pix_price"] = sd.format_brl(p["pix_price"])
    return fields


def _summary(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p["product_id"],
        "name": p["name"],
        "availability": p["availability"],
        **_price_fields(p),
    }


def _summaries(products: pd.DataFrame) -> list[dict[str, Any]]:
    return [_summary(p) for p in products.to_dict("records")]


def _token_score(query: str, word: str) -> float:
    # A query token may be a prefix of a longer word ("strato"), never the other way round.
    return (
        fuzz.partial_ratio(query, word)
        if len(query) <= len(word)
        else fuzz.ratio(query, word)
    )


def _match_products(products: pd.DataFrame, name_or_id: str) -> list[int]:
    """Ids matching a product id or an approximate name; more than one means ambiguous."""
    key = name_or_id.strip()
    if key.isdigit():
        return [int(key)] if int(key) in products.index else []
    tokens = sd.search_key(key).split()
    if not tokens:
        return []
    scores = {
        pid: sum(max(_token_score(t, w) for w in words) for t in tokens) / len(tokens)
        for pid, words in products["name"]
        .map(lambda n: sd.search_key(n).split())
        .items()
    }
    best = max(scores.values())
    if best < FUZZY_MIN_SCORE:
        return []
    close = sorted(
        (s, pid) for pid, s in scores.items() if s >= best - FUZZY_AMBIGUITY_MARGIN
    )
    return [pid for _, pid in reversed(close)][:MAX_CANDIDATES]


def _alternatives(products: pd.DataFrame, p: dict[str, Any]) -> list[dict[str, Any]]:
    """Available products in the same category, closest in price first."""
    pool = products[
        (products["category_id"] == p["category_id"])
        & (products["availability"] == "available")
    ]
    distance = pool["effective_price"].map(
        lambda price: abs(price - p["effective_price"])
    )
    return _summaries(pool.loc[distance.sort_values().index[:MAX_ALTERNATIVES]])


def search_products(
    query: str = "",
    category: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    only_available: bool = True,
) -> dict[str, Any]:
    """Search the instrument catalog for options, availability and price ranges.

    query matches name, brand and specs (e.g. "nylon", "Yamaha", "elétrico"). category takes
    terms like "violão", "guitarra", "baixo", "bateria", "teclado", "ukulele", "sopro", "violino".
    Price filters use the price the customer pays today (the promotional price when there is one).
    Returns up to 8 products sorted by price and the total number of matches.
    """
    products = _store().products
    if category:
        ids = sd.resolve_category(category)
        if ids is None:
            return {
                "error": f"Unknown category '{category}'.",
                "known_categories": sorted(set(products["category"])),
            }
        products = products[products["category_id"].isin(ids)]
        if products.empty:
            return {
                "showing": "0 of 0",
                "notice": "The store carries this category but has no products in the catalog right now. "
                "Say 'no momento não temos', never 'não vendemos'.",
            }
    tokens = [t for t in sd.search_key(query).split() if t not in STOPWORDS]
    products = products[
        products["search_text"].map(lambda text: all(t in text for t in tokens))
    ]
    if only_available:
        products = products[products["availability"] == "available"]
    if max_price is not None:
        products = products[products["effective_price"] <= Decimal(str(max_price))]
    if min_price is not None:
        products = products[products["effective_price"] >= Decimal(str(min_price))]
    products = products.sort_values("effective_price")
    shown = products.head(MAX_SEARCH_RESULTS)
    return {
        "showing": f"{len(shown)} of {len(products)}",
        "products": _summaries(shown),
    }


def get_product_details(name_or_id: str) -> dict[str, Any]:
    """Get one product's full details: price (promotion with original price and discount, or the
    PIX price), maximum interest-free installments, specs, ended promotions and, when it is not
    for sale, up to 3 available alternatives. Accepts an id or an approximate name such as
    "Takamine GD20". If several products match, returns the candidates: ask which one.
    """
    products = _store().products
    ids = _match_products(products, name_or_id)
    if not ids:
        return {
            "error": "No product matches this name. Try search_products with fewer words."
        }
    if len(ids) > 1:
        return {"ambiguous": True, "candidates": _summaries(products.loc[ids])}
    p = products.loc[ids[0]].to_dict()
    count, value = p["installments"]
    details = {
        **_summary(p),
        "category": p["category"],
        "installments": f"até {count}x de {sd.format_brl(value)} sem juros"
        if count > 1
        else "somente à vista",
        "specs": p["specs"],
    }
    if not p["description_conflict"]:
        details["description"] = p["description"]
    if p["ended_promotions"]:
        details["ended_promotions"] = [
            f"{promo} - ended, no longer valid" for promo in p["ended_promotions"]
        ]
    if p["availability"] != "available":
        details["alternatives"] = _alternatives(products, p)
    return details


def list_active_promotions() -> dict[str, Any]:
    """List the promotions active today with original price, discount and promotional price."""
    products = _store().products
    promos = products[products["promo_percent"] > 0].sort_values(
        "promo_percent", ascending=False
    )
    return {"promotions": _summaries(promos)}


def _br_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _payment_label(method: str) -> str:
    if method.startswith("credit_"):
        return f"cartão de crédito em {method.removeprefix('credit_')}"
    return PAYMENT_METHODS.get(method, method)


def _order_view(order: dict[str, Any], today: date) -> dict[str, Any]:
    store = _store()
    items = store.order_items[store.order_items["order_id"] == order["order_id"]]
    names = store.products["name"]
    view: dict[str, Any] = {
        "order_id": order["order_id"],
        "order_date": _br_date(order["order_date"]),
        "status": ORDER_STATUS[order["status"]],
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
        windows = sd.return_windows(order["order_date"], eta, today)
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
    store = _store()
    today = runtime.context.now.date()
    customer_ids = sd.find_customer_ids(store.customers, contact)
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
    if not summary or not contact:
        return {
            "error": "Ask for a short summary of the issue and an e-mail or phone first."
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
    return {"protocol": protocol, "response_time": TICKET_RESPONSE_TIME}


TOOLS = [
    search_products,
    get_product_details,
    list_active_promotions,
    lookup_orders,
    get_store_policy,
    open_support_ticket,
]
