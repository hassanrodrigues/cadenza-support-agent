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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2199", "R$ 2.199,00"),
        ("1967.18", "R$ 1.967,18"),
        ("599.9", "R$ 599,90"),
        ("12500", "R$ 12.500,00"),
    ],
)
def test_format_brl_uses_brazilian_separators(value, expected):
    assert sd.format_brl(Decimal(value)) == expected


@pytest.mark.parametrize(
    ("product_id", "expected"),
    [
        (95, "available"),
        (96, "out_of_stock"),
        (113, "discontinued"),
        (136, "discontinued"),
        (130, "coming_soon"),
    ],
)
def test_status_wins_over_stock(store, product_id, expected):
    assert store.products.loc[product_id, "availability"] == expected


def test_only_four_promotions_are_active(store):
    promo = store.products[store.products["promo_percent"] > 0][
        "promo_percent"
    ].to_dict()
    assert promo == {90: 18, 94: 8, 121: 20, 127: 10}


def test_promo_price_is_rounded_to_cents_and_has_no_pix(store):
    crafter, taylor = store.products.loc[90], store.products.loc[94]
    assert crafter["effective_price"] == Decimal("1967.18")
    assert taylor["effective_price"] == Decimal("5519.08")
    assert taylor["pix_price"] is None


def test_pix_price_applies_only_without_promotion(store):
    takamine = store.products.loc[95]
    assert takamine["promo_percent"] == 0
    assert takamine["effective_price"] == Decimal("2199.00")
    assert takamine["pix_price"] == Decimal("2089.05")


def test_ended_promotions_are_kept_for_transparency(store):
    assert store.products.loc[95, "ended_promotions"] == ["12% (Oferta Especial)"]
    assert len(store.products.loc[93, "ended_promotions"]) == 2


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        ("2199", (12, "183.25")),
        ("1199", (11, "109.00")),
        ("500", (6, "83.33")),
        ("250", (3, "83.33")),
        ("120", (2, "60.00")),
        ("40", (1, "40.00")),
    ],
)
def test_max_installments_follow_manual_tiers(price, expected):
    count, value = sd.max_installments(Decimal(price).quantize(sd.CENT))
    assert (count, str(value)) == expected


def test_installments_use_the_promotional_price(store):
    assert store.products.loc[90, "installments"] == (12, Decimal("163.93"))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(67) 99812-3456", "67998123456"),
        ("+55 67 99812-3456", "67998123456"),
        ("(55) 99999-1234", "55999991234"),
        ("+55 (55) 99999-1234", "55999991234"),
        ("(67) 3341-4444", "6733414444"),
        ("99812-3456", None),
        ("3456", None),
    ],
)
def test_normalize_phone_requires_area_code_and_keeps_ddd_55(raw, expected):
    assert sd.normalize_phone(raw) == expected


def test_find_customer_ids_by_email_phone_or_none_for_partial_phone(store):
    assert sd.find_customer_ids(store.customers, " Lucas.Mendes@jmail.com ") == [1]
    assert sd.find_customer_ids(store.customers, "67 99812 3456") == [1]
    assert sd.find_customer_ids(store.customers, "bruno.martins@jmail.com") == [11, 43]
    assert sd.find_customer_ids(store.customers, "nobody@jmail.com") == []
    assert sd.find_customer_ids(store.customers, "3456") is None


def test_return_windows_are_inclusive_and_use_the_right_start_date():
    ordered, delivered = date(2026, 2, 3), date(2026, 2, 17)
    on_last_day = sd.return_windows(ordered, delivered, date(2026, 2, 24))
    assert on_last_day["regret_return"] == sd.ReturnWindow(True, date(2026, 2, 24))
    assert on_last_day["defect_exchange"].deadline == date(2026, 3, 5)
    assert on_last_day["legal_warranty"].deadline == date(2026, 5, 18)
    day_after = sd.return_windows(ordered, delivered, date(2026, 2, 25))
    assert not day_after["regret_return"].eligible
    assert not day_after["preference_exchange"].eligible
    assert day_after["defect_exchange"].eligible
