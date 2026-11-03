from datetime import date
from decimal import Decimal

import pytest

from cadenza import store_data as sd
from cadenza.context import DATA_DIR


@pytest.fixture(scope="module")
def store():
    return sd.load_store(DATA_DIR)


def test_loads_every_table_with_expected_row_counts(store):
    assert len(store.products) == 65
    assert len(store.customers) == 50
    assert len(store.orders) == 20
    assert len(store.promotions) == 25


def test_products_count_per_category_matches_profiling(store):
    counts = store.products["category_id"].value_counts().to_dict()
    assert counts == {5: 35, 9: 15, 1: 5, 2: 4, 3: 3, 4: 3}


def test_prices_are_exact_decimals(store):
    assert store.products.loc[81, "price"] == Decimal("599.90")


def test_specs_are_parsed_into_dicts(store):
    assert store.products.loc[95, "specs"]["strings"] == "steel"


def test_normalize_text_lowercases_and_strips_accents():
    assert sd.normalize_text("Violão Elétrico AÇO") == "violao eletrico aco"


def test_brand_skips_generic_prefixes_and_keeps_multiword_brands():
    assert sd.extract_brand("Bateria Acústica Pearl Kit 2 Studio") == "pearl"
    assert sd.extract_brand("Teclado Sintetizador Nord Synth 2 Pro") == "nord"
    assert sd.extract_brand("Music Man Bass 1X Electric Bass") == "music man"


def test_description_conflicts_are_exactly_the_seven_known_products(store):
    flagged = store.products.index[store.products["description_conflict"]].tolist()
    assert flagged == [135, 136, 137, 139, 140, 142, 144]


def test_conflicting_description_is_left_out_of_search_text(store):
    assert "fender" not in store.products.loc[135, "search_text"]
    assert "stingray" in store.products.loc[138, "search_text"]


def test_search_text_includes_category_aliases(store):
    assert "violao" in store.products.loc[95, "search_text"]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("Violões", [5]),
        ("piano", [4]),
        ("sopro", [6, 7]),
        ("violino", [8]),
        ("pandeiro azul", None),
    ],
)
def test_resolve_category_maps_customer_terms(term, expected):
    assert sd.resolve_category(term) == expected


def test_customer_contacts_are_normalized(store):
    first = store.customers.iloc[0]
    assert first["phone_digits"] == "67998123456"
    assert first["email"] == first["email"].lower()


def test_order_dates_are_parsed_and_missing_ones_are_none(store):
    orders = store.orders.set_index("order_id")
    assert orders.loc[7, "estimated_delivery"] == date(2026, 2, 17)
    assert orders.loc[9, "estimated_delivery"] is None
