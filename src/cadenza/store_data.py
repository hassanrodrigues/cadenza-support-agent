"""Store data: load the CSVs and derive prices, availability and order rules."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

CENT = Decimal("0.01")

# Normalized aliases customers use for each category_id. "sopro" covers both wind categories.
CATEGORY_ALIASES = {
    1: ("guitarra", "guitarras"),
    2: ("baixo", "baixos", "contrabaixo", "contrabaixos"),
    3: ("bateria", "baterias", "percussao"),
    4: ("teclado", "teclados", "piano", "pianos", "sintetizador"),
    5: ("violao", "violoes"),
    6: ("sopro", "sopros", "madeiras", "flauta", "clarinete", "saxofone", "sax"),
    7: ("sopro", "sopros", "metais", "trompete", "trombone"),
    8: ("cordas orquestrais", "violino", "violinos", "violoncelo", "cello"),
    9: ("ukulele", "ukuleles"),
}

# Generic words that come before the brand in some product names ("Bateria Acústica Pearl ...").
NAME_PREFIXES = {"bateria", "acustica", "teclado", "sintetizador"}
MULTIWORD_BRANDS = ("music man",)
# Only these categories name the brand in the description, so a mismatch there is a conflict.
BRANDED_DESCRIPTION_CATEGORIES = {1, 2, 3, 4}


@dataclass(frozen=True)
class Store:
    """All store tables, already normalized."""

    products: pd.DataFrame
    customers: pd.DataFrame
    orders: pd.DataFrame
    order_items: pd.DataFrame
    promotions: pd.DataFrame


def normalize_text(text: str) -> str:
    """Lowercase and strip accents, for matching."""
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def to_money(value: float | str) -> Decimal:
    """Convert a CSV price to Decimal cents without float noise."""
    return Decimal(str(value)).quantize(CENT, ROUND_HALF_UP)


def resolve_category(text: str) -> list[int] | None:
    """Category ids matching a customer term, or None if the term is unknown."""
    term = normalize_text(text).strip()
    ids = [cid for cid, aliases in CATEGORY_ALIASES.items() if term in aliases]
    return ids or None


def extract_brand(name: str) -> str:
    """Brand from a product name, skipping generic prefixes."""
    words = normalize_text(name).split()
    while words and words[0] in NAME_PREFIXES:
        words.pop(0)
    rest = " ".join(words)
    return next(
        (b for b in MULTIWORD_BRANDS if rest.startswith(b)), words[0] if words else ""
    )


def has_description_conflict(name: str, description: str, category_id: int) -> bool:
    """True when the description does not mention the brand in the product name."""
    if category_id not in BRANDED_DESCRIPTION_CATEGORIES:
        return False
    return extract_brand(name) not in normalize_text(description)


def _search_text(row: pd.Series) -> str:
    parts = [
        row["name"],
        row["category"],
        *row["specs"].values(),
        *CATEGORY_ALIASES[row["category_id"]],
    ]
    if not row["description_conflict"]:
        parts.append(row["description"])
    return normalize_text(" ".join(map(str, parts)))


def _parse_date(value: object) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def _prepare_products(products: pd.DataFrame, categories: pd.DataFrame) -> pd.DataFrame:
    products = products.copy()
    products["price"] = products["price_brl"].map(to_money)
    products["specs"] = products["specs"].map(json.loads)
    products["category"] = products["category_id"].map(
        categories.set_index("category_id")["name"]
    )
    products["description_conflict"] = [
        has_description_conflict(n, d, c)
        for n, d, c in zip(
            products["name"], products["description"], products["category_id"]
        )
    ]
    products["search_text"] = products.apply(_search_text, axis=1)
    return products.set_index("product_id", drop=False)


def load_store(data_dir: Path) -> Store:
    """Load and normalize every CSV in data_dir."""

    def read(name: str) -> pd.DataFrame:
        return pd.read_csv(data_dir / f"{name}.csv", encoding="utf-8")

    customers = read("customers")
    customers["phone_digits"] = customers["phone"].str.replace(r"\D", "", regex=True)
    customers["email"] = customers["email"].str.strip().str.lower()
    orders = read("orders")
    for column in ("order_date", "estimated_delivery"):
        orders[column] = orders[column].map(_parse_date)
    return Store(
        products=_prepare_products(read("products"), read("categories")),
        customers=customers,
        orders=orders,
        order_items=read("order_items"),
        promotions=read("promotions"),
    )
