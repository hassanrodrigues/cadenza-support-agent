"""Tools exposed to the LLM. Each docstring is part of the prompt."""

from __future__ import annotations

from decimal import Decimal
from functools import cache
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from cadenza import store_data as sd
from cadenza.context import DATA_DIR

MAX_SEARCH_RESULTS = 8
MAX_ALTERNATIVES = 3
MAX_CANDIDATES = 5
FUZZY_MIN_SCORE = 80
FUZZY_AMBIGUITY_MARGIN = 5
STOPWORDS = {
    "a",
    "o",
    "as",
    "os",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "com",
    "para",
    "um",
    "uma",
}


@cache
def _store() -> sd.Store:
    return sd.load_store(DATA_DIR)


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


TOOLS = [search_products, get_product_details, list_active_promotions]
